# Fraud Detection System - Deployment Guide

## 🚀 Quick Start (Development)

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Train models
python train_models.py

# 3. Run Streamlit app
streamlit run app.py
```
Access: `http://localhost:8501`

---

## 🐳 Docker Deployment (Recommended)

### Step 1: Create Dockerfile
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8501
HEALTHCHECK CMD curl --fail http://localhost:8501/_stcore/health || exit 1
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
```

### Step 2: Build & Run
```bash
# Build
docker build -t fraud-detection:latest .

# Run
docker run -p 8501:8501 \
  -v $(pwd)/artifacts:/app/artifacts \
  -v $(pwd)/data:/app/data \
  fraud-detection:latest
```

### Step 3: Push to Docker Hub
```bash
docker tag fraud-detection:latest yourusername/fraud-detection:latest
docker push yourusername/fraud-detection:latest
```

---

## ☁️ Cloud Deployment Options

### **AWS (Fastest enterprise option)**

#### Option A: EC2 + Docker
```bash
# SSH into EC2
ssh -i key.pem ec2-user@instance-ip

# Install Docker
sudo amazon-linux-extras install docker
sudo service docker start

# Pull and run image
docker pull yourusername/fraud-detection:latest
docker run -d -p 8501:8501 yourusername/fraud-detection:latest
```

#### Option B: AWS App Runner
```bash
aws apprunner create-service \
  --service-name fraud-detection \
  --source-configuration "{
    \"ImageRepository\": {
      \"ImageIdentifier\": \"yourusername/fraud-detection:latest\",
      \"RepositoryType\": \"ECR_PUBLIC\"
    },
    \"Port\": \"8501\"
  }"
```

#### Option C: SageMaker (Best for ML models)
```bash
# Package model for SageMaker
tar -czf model.tar.gz artifacts/

# Upload to S3
aws s3 cp model.tar.gz s3://your-bucket/fraud-detection/

# Create endpoint via AWS Console or CLI
aws sagemaker create-model \
  --model-name fraud-detection-model \
  --primary-container Image=...]
```

---

### **Azure**

```bash
# Login
az login

# Create resource group
az group create --name rg-fraud --location eastus

# Create App Service Plan
az appservice plan create \
  --name plan-fraud \
  --resource-group rg-fraud \
  --sku B1

# Create Web App
az webapp create \
  --resource-group rg-fraud \
  --plan plan-fraud \
  --name fraud-detection-app \
  --deployment-container-image-name yourusername/fraud-detection:latest

# Configure container
az webapp config container set \
  --resource-group rg-fraud \
  --name fraud-detection-app \
  --docker-custom-image-name yourusername/fraud-detection:latest \
  --docker-registry-server-url https://index.docker.io \
  --docker-registry-server-user youruser \
  --docker-registry-server-password yourpass
```

---

### **Google Cloud**

```bash
# Authenticate
gcloud auth login

# Create GCP project
gcloud projects create fraud-detection-project

# Enable services
gcloud services enable run.googleapis.com

# Deploy to Cloud Run
gcloud run deploy fraud-detection \
  --image yourusername/fraud-detection:latest \
  --platform managed \
  --region us-central1 \
  --port 8501 \
  --memory 1Gi \
  --cpu 1 \
  --timeout 3600
```

---

## 🔧 FastAPI Model Serving (For API integration)

### Create API server:
```python
# api.py
from fastapi import FastAPI
from pydantic import BaseModel
import joblib
import numpy as np

app = FastAPI()

# Load models
scaler = joblib.load('artifacts/scaler.pkl')
selector = joblib.load('artifacts/selector.pkl')
model = joblib.load('artifacts/best_model.pkl')

class Transaction(BaseModel):
    amount: float
    merchant_id: int
    transaction_type: str
    location: str
    hour: int
    day_of_week: int
    month: int
    is_weekend: int
    is_night_txn: int

@app.post("/predict")
async def predict(txn: Transaction):
    features = np.array([[
        txn.amount, txn.merchant_id, txn.transaction_type, txn.location,
        txn.hour, txn.day_of_week, txn.month, txn.is_weekend, txn.is_night_txn
    ]])
    features_scaled = scaler.transform(features)
    features_selected = selector.transform(features_scaled)
    prob = model.predict_proba(features_selected)[0, 1]
    return {"probability": float(prob), "is_fraud": int(prob >= 0.5)}

@app.get("/health")
async def health():
    return {"status": "healthy"}
```

### Deploy FastAPI:
```bash
# Local
uvicorn api:app --reload --host 0.0.0.0 --port 8000

# Production
pip install gunicorn
gunicorn api:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

---

## 🔄 CI/CD Pipeline (GitHub Actions)

Create `.github/workflows/deploy.yml`:
```yaml
name: Deploy Fraud Detection

on:
  push:
    branches: [ main ]

jobs:
  build-and-deploy:
    runs-on: ubuntu-latest
    
    steps:
    - uses: actions/checkout@v2
    
    - name: Set up Python
      uses: actions/setup-python@v2
      with:
        python-version: 3.11
    
    - name: Install dependencies
      run: |
        pip install -r requirements.txt
    
    - name: Run tests
      run: |
        python -m pytest tests/
    
    - name: Train models
      run: |
        python train_models.py
    
    - name: Build Docker image
      run: |
        docker build -t fraud-detection:${{ github.sha }} .
        docker tag fraud-detection:${{ github.sha }} fraud-detection:latest
    
    - name: Push to Docker Hub
      run: |
        echo "${{ secrets.DOCKER_PASSWORD }}" | docker login -u "${{ secrets.DOCKER_USERNAME }}" --password-stdin
        docker push yourusername/fraud-detection:latest
    
    - name: Deploy to AWS
      run: |
        aws apprunner start-deployment \
          --service-arn arn:aws:apprunner:region:account:service/fraud-detection/id
      env:
        AWS_ACCESS_KEY_ID: ${{ secrets.AWS_ACCESS_KEY_ID }}
        AWS_SECRET_ACCESS_KEY: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
```

---

## 📊 Monitoring & Alerts

### CloudWatch Dashboard (AWS)
```python
import boto3

cloudwatch = boto3.client('cloudwatch')

def log_prediction(prediction, probability, latency):
    cloudwatch.put_metric_data(
        Namespace='FraudDetection',
        MetricData=[
            {
                'MetricName': 'PredictionLatency',
                'Value': latency,
                'Unit': 'Milliseconds'
            },
            {
                'MetricName': 'FraudPredictions',
                'Value': prediction,
                'Unit': 'Count'
            }
        ]
    )
```

### Datadog (Multi-cloud)
```yaml
# datadog.yaml
agent:
  log_level: info
  
logs:
  enabled: true
  
apm:
  enabled: true
  
metrics:
  - name: fraud_detection.predictions
    type: gauge
    help: Number of fraud predictions
```

---

## 🔐 Security Best Practices

### 1. Environment Variables
```bash
# .env
STREAMLIT_SERVER_PORT=8501
STREAMLIT_SERVER_ADDRESS=0.0.0.0
MODEL_PATH=/app/artifacts/
DATA_PATH=/app/data/
DATABASE_URL=postgresql://user:pass@localhost/frauddb
API_KEY=your-secret-key
```

### 2. Docker Security
```dockerfile
# Run as non-root user
RUN useradd -m -u 1000 mluser
USER mluser

# Do not cache pip
RUN pip install --no-cache-dir -r requirements.txt

# Minimize image size
FROM python:3.11-slim
```

### 3. Model Versioning
```python
# Store model versions
model_version = "v1.0"
model_hash = hashlib.sha256(open('artifacts/best_model.pkl', 'rb').read()).hexdigest()

metadata = {
    "version": model_version,
    "hash": model_hash,
    "timestamp": datetime.now().isoformat(),
    "roc_auc": 0.5132
}

with open('artifacts/model_metadata.json', 'w') as f:
    json.dump(metadata, f)
```

---

## 📈 Scaling Strategies

### Horizontal Scaling (Multiple instances)
```bash
# Docker Compose with multiple services
version: '3.8'
services:
  app1:
    image: fraud-detection:latest
    ports: ["8501:8501"]
  app2:
    image: fraud-detection:latest
    ports: ["8502:8501"]
  app3:
    image: fraud-detection:latest
    ports: ["8503:8501"]
  
  nginx:
    image: nginx:latest
    ports: ["80:80"]
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
```

### Kubernetes Auto-scaling
```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: fraud-detection-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: fraud-detection
  minReplicas: 2
  maxReplicas: 10
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
```

---

## 🧪 Pre-Deployment Checklist

- [ ] All tests passing (`pytest tests/`)
- [ ] Code linted (`flake8`, `black`)
- [ ] Security scan completed (`bandit`)
- [ ] Docker image builds successfully
- [ ] Models trained and artifacts saved
- [ ] Environment variables configured
- [ ] Database migrations completed
- [ ] Monitoring dashboards created
- [ ] Alert thresholds set
- [ ] Runbooks documented
- [ ] Incident response plan ready
- [ ] Backup strategy in place
- [ ] Load testing completed
- [ ] Documentation updated
- [ ] Team training completed

---

## 🚨 Troubleshooting

### Docker won't build
```bash
# Check Docker daemon
docker ps

# Build with verbose output
docker build -t fraud-detection . --progress=plain

# Check logs
docker logs <container_id>
```

### App crashing on startup
```bash
# Check if models exist
ls -la artifacts/

# Verify permissions
chmod 644 artifacts/*.pkl

# Run in debug mode
streamlit run app.py --logger.level=debug
```

### Model serving slow
```bash
# Profile predictions
import time
start = time.time()
prediction = model.predict(X)
print(f"Inference time: {time.time() - start:.3f}s")

# Consider using ONNX
pip install onnx onnxruntime
# Convert model for faster inference
```

---

## 📞 Support & Contact

- **Documentation**: See PROJECT_SUMMARY.md
- **Issues**: GitHub Issues
- **Slack**: #fraud-detection-team
- **Oncall**: PagerDuty

---

**Last Updated**: March 31, 2026  
**Status**: Production Ready ✅

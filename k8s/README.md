# Kubernetes 배포 매니페스트

이 디렉토리에는 각 서비스의 Kubernetes 배포 매니페스트 파일들이 포함되어 있습니다.

## 디렉토리 구조

```
k8s/
├── ai-chat-service/
│   ├── deployment.yaml    # Deployment 매니페스트
│   └── service.yaml       # Service 매니페스트
└── ai-vision-service/
    ├── deployment.yaml    # Deployment 매니페스트
    └── service.yaml       # Service 매니페스트
```

## 파일 설명

### deployment.yaml
- Pod의 배포 설정
- 이미지, 리소스, 헬스체크, 환경 변수 등 포함
- 이미지 태그는 배포 스크립트에서 동적으로 치환됩니다

### service.yaml
- Kubernetes Service 정의
- 클러스터 내부 통신을 위한 엔드포인트 제공

## 사용법

### 로컬 테스트
```bash
# 이미지 빌드
./scripts/build-local.sh ai-chat-service

# Kubernetes 배포 (k8s 폴더의 YAML 사용)
./scripts/deploy-local.sh ai-chat-service
```

### 직접 kubectl로 배포
```bash
# 네임스페이스 생성
kubectl create namespace jiaa-dev

# 이미지 태그 치환 후 배포
sed "s|image: jiaa-ai-chat-service:local|image: jiaa-ai-chat-service:v1.0.0|g" \
    k8s/ai-chat-service/deployment.yaml | \
    kubectl apply -f -

kubectl apply -f k8s/ai-chat-service/service.yaml
```

## AWS 자격 증명 설정

Bedrock을 사용하기 위해서는 AWS 자격 증명이 필요합니다. Kubernetes Secret으로 관리합니다.

### 방법 1: 스크립트 사용 (권장)

```bash
# 환경 변수로 설정
export AWS_ACCESS_KEY_ID=your-access-key-id
export AWS_SECRET_ACCESS_KEY=your-secret-access-key
export AWS_REGION=us-east-1

# Secret 생성
./scripts/create-aws-secret.sh default
```

### 방법 2: kubectl 명령어 직접 사용

```bash
kubectl create secret generic aws-credentials \
  --from-literal=AWS_ACCESS_KEY_ID=your-access-key-id \
  --from-literal=AWS_SECRET_ACCESS_KEY=your-secret-access-key \
  --from-literal=AWS_REGION=us-east-1 \
  -n default
```

### 방법 3: YAML 파일 사용

`k8s/aws-secret.yaml.example` 파일을 참고하여 Secret을 생성하세요.

**보안 주의사항**: 
- Secret YAML 파일은 절대 Git에 커밋하지 마세요
- 프로덕션 환경에서는 AWS IAM Role for Service Account (IRSA) 사용을 권장합니다

## 주의사항

- 이미지 태그는 배포 스크립트에서 자동으로 치환됩니다
- 네임스페이스는 배포 스크립트나 `kubectl apply -n <namespace>`로 지정할 수 있습니다
- AWS 자격 증명은 Secret으로 관리되며, Deployment에서 자동으로 참조됩니다
- 프로덕션 환경에서는 AWS IAM Role for Service Account (IRSA) 사용을 권장합니다


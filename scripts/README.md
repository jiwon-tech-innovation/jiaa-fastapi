# 로컬 Kubernetes 테스트 스크립트

이 디렉토리에는 로컬 Kubernetes 환경에서 서비스를 테스트하기 위한 스크립트들이 포함되어 있습니다.

## 스크립트 사용법

### 1. build-local.sh
Docker 이미지를 빌드합니다.

```bash
# 기본 사용 (ai-chat-service)
./scripts/build-local.sh

# 특정 서비스 빌드
./scripts/build-local.sh ai-chat-service
./scripts/build-local.sh ai-vision-service

# 커스텀 태그 지정
./scripts/build-local.sh ai-chat-service v1.0.0
```

### 2. deploy-local.sh
로컬 Kubernetes 클러스터에 배포합니다. `k8s/` 폴더의 YAML 파일을 사용합니다.

```bash
# 기본 사용
./scripts/deploy-local.sh

# 특정 서비스 배포
./scripts/deploy-local.sh ai-chat-service

# 커스텀 이미지 태그 및 포트 지정
./scripts/deploy-local.sh ai-chat-service local 8000

# 네임스페이스 지정
./scripts/deploy-local.sh ai-chat-service local jiaa-dev 8000
```

**참고**: 이 스크립트는 `k8s/<service-name>/deployment.yaml`과 `k8s/<service-name>/service.yaml` 파일을 자동으로 사용하며, 이미지 태그와 네임스페이스를 동적으로 치환합니다.

### 3. port-forward.sh
Pod에 포트 포워딩합니다.

```bash
# 기본 사용 (로컬 포트 8000)
./scripts/port-forward.sh ai-chat-service

# 커스텀 로컬 포트 지정
./scripts/port-forward.sh ai-chat-service 3000

# 네임스페이스 및 서비스 포트 지정
./scripts/port-forward.sh ai-chat-service 3000 default 8000
```

### 4. cleanup-local.sh
로컬 Kubernetes 리소스를 정리합니다.

```bash
# 기본 사용
./scripts/cleanup-local.sh

# 특정 서비스 정리
./scripts/cleanup-local.sh ai-chat-service

# 이미지도 함께 삭제
./scripts/cleanup-local.sh ai-chat-service local default --remove-image
```

### 5. create-aws-secret.sh
AWS 자격 증명을 Kubernetes Secret으로 생성합니다. Bedrock 사용에 필요합니다.

```bash
# 대화형으로 입력받아 생성
./scripts/create-aws-secret.sh default

# 환경 변수 사용
export AWS_ACCESS_KEY_ID=your-access-key-id
export AWS_SECRET_ACCESS_KEY=your-secret-access-key
export AWS_REGION=us-east-1
./scripts/create-aws-secret.sh default
```

## 전체 워크플로우 예시

```bash
# 0. AWS 자격 증명 Secret 생성 (최초 1회)
./scripts/create-aws-secret.sh default

# 1. 이미지 빌드
./scripts/build-local.sh ai-chat-service

# 2. Kubernetes에 배포
./scripts/deploy-local.sh ai-chat-service

# 3. 포트 포워딩 (새 터미널에서)
./scripts/port-forward.sh ai-chat-service 8000

# 4. 테스트 완료 후 정리
./scripts/cleanup-local.sh ai-chat-service local default --remove-image
```

## Kubernetes 매니페스트

모든 Kubernetes 배포 매니페스트는 `k8s/` 폴더에 저장되어 있습니다:
- `k8s/ai-chat-service/deployment.yaml` - ai-chat-service Deployment
- `k8s/ai-chat-service/service.yaml` - ai-chat-service Service
- `k8s/ai-vision-service/deployment.yaml` - ai-vision-service Deployment
- `k8s/ai-vision-service/service.yaml` - ai-vision-service Service

자세한 내용은 [k8s/README.md](../k8s/README.md)를 참조하세요.

## 요구사항

- Docker
- kubectl
- Kubernetes 클러스터 (로컬: kind, minikube 등)
- 실행 권한 (chmod +x scripts/*.sh)

## 스크립트에 실행 권한 부여

```bash
chmod +x scripts/*.sh
```


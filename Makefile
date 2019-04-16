.PHONY: build push

DEPLOY_NAMESPACE = moop-dev
TAG			= $(shell git describe --tags --always)
REGISTRY	= registry.datadynamic.io/moop
IMAGE		= moop-launcher-service


build: 
	docker build --rm -t "$(REGISTRY)/$(IMAGE):$(TAG)" -f Dockerfile .

push: build
	docker push "$(REGISTRY)/$(IMAGE):$(TAG)"

# deploy: push
# 	kubectl apply -f deploy/ --namespace "$(DEPLOY_NAMESPACE)"

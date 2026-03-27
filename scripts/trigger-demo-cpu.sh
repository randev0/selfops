#!/bin/bash
echo "Triggering CPU stress on demo app..."
DEMO_POD=$(kubectl get pods -n platform -l app=selfops-demo-app -o jsonpath='{.items[0].metadata.name}')
kubectl exec -n platform $DEMO_POD -- curl -s localhost:8080/stress-cpu
echo "Done. CPU alert should fire in ~2 minutes."

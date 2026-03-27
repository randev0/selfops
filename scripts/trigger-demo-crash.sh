#!/bin/bash
echo "Triggering demo app crash..."
DEMO_POD=$(kubectl get pods -n platform -l app=selfops-demo-app -o jsonpath='{.items[0].metadata.name}')
kubectl exec -n platform $DEMO_POD -- curl -s localhost:8080/crash
echo "Done. Watch the SelfOps dashboard for the incident."

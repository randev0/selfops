#!/bin/bash
echo "Starting port forwards for local development..."
kubectl port-forward -n platform svc/selfops-api 8000:8000 &
kubectl port-forward -n platform svc/selfops-frontend 3000:3000 &
kubectl port-forward -n monitoring svc/kube-prom-grafana 3001:80 &
kubectl port-forward -n monitoring svc/prometheus-operated 9090:9090 &
kubectl port-forward -n monitoring svc/kube-prom-kube-prometheus-alertmanager 9093:9093 &
echo "All port forwards started."
echo "  API:           http://localhost:8000/api/docs"
echo "  Frontend:      http://localhost:3000"
echo "  Grafana:       http://localhost:3001"
echo "  Prometheus:    http://localhost:9090"
echo "  Alertmanager:  http://localhost:9093"

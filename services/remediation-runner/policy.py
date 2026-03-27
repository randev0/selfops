ALLOWED_ACTIONS = {
    "restart_deployment": {
        "name": "Restart Deployment",
        "description": "Performs a rollout restart of the specified deployment",
        "playbook": "remediation/restart_deployment.yml",
        "safe_for_auto": False,
        "required_params": ["deployment_name", "namespace"],
        "allowed_namespaces": ["platform"],
    },
    "rollout_restart": {
        "name": "Rollout Restart",
        "description": "Graceful rolling restart that replaces pods one at a time",
        "playbook": "remediation/rollout_restart.yml",
        "safe_for_auto": False,
        "required_params": ["deployment_name", "namespace"],
        "allowed_namespaces": ["platform"],
    },
    "scale_up": {
        "name": "Scale Up Replicas",
        "description": "Increases replica count by 1, up to a maximum of 4",
        "playbook": "remediation/scale_up.yml",
        "safe_for_auto": False,
        "required_params": ["deployment_name", "namespace", "max_replicas"],
        "allowed_namespaces": ["platform"],
    },
}


def validate_action(action_id: str, params: dict) -> tuple[bool, str]:
    if action_id not in ALLOWED_ACTIONS:
        return False, f"Action '{action_id}' is not in the allowed list"
    action = ALLOWED_ACTIONS[action_id]
    for param in action["required_params"]:
        if param not in params:
            return False, f"Missing required parameter: {param}"
    namespace = params.get("namespace")
    if namespace and namespace not in action["allowed_namespaces"]:
        return False, f"Namespace '{namespace}' is not allowed for this action"
    return True, "ok"

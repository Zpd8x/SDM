def register(context):
    """Example no-op plugin. Enable a copy from System Center when developing."""
    return {"status": "ready", "api": context.get("plugin_api_version")}

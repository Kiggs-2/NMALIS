from django.core.checks import Warning, register


@register()
def check_reportlab_installed(app_configs, **kwargs):
    if app_configs is not None and "registry" not in {
        app.label for app in app_configs
    }:
        return []
    try:
        import reportlab  # noqa: F401
    except ImportError:
        return [
            Warning(
                "ReportLab is not installed. PDF certificate downloads will fail until you run "
                "`pip install -r requirements.txt`.",
                id="registry.W001",
            )
        ]
    return []

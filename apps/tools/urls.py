from django.urls import path

from . import views

app_name = "tools"

urlpatterns = [
    path("<uuid:workspace_id>/", views.tool_list, name="list"),
    path("<uuid:workspace_id>/upload/", views.tool_upload, name="upload"),
    path("<uuid:workspace_id>/history/", views.tool_history, name="history"),
    path("<uuid:workspace_id>/<uuid:tool_id>/launch/", views.tool_launch, name="launch"),
    path("<uuid:workspace_id>/<uuid:tool_id>/return/", views.tool_return, name="return"),
    path("<uuid:workspace_id>/<uuid:tool_id>/force-return/", views.tool_force_return, name="force_return"),
    path("<uuid:workspace_id>/<uuid:tool_id>/update-cookies/", views.tool_update_cookies, name="update_cookies"),
    path("<uuid:workspace_id>/<uuid:tool_id>/delete/", views.tool_delete, name="delete"),
]

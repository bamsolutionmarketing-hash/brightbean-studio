from django.urls import path

from . import views

app_name = "tools"

urlpatterns = [
    path("<uuid:workspace_id>/", views.tool_list, name="list"),
    path("<uuid:workspace_id>/upload/", views.tool_upload, name="upload"),
    path("<uuid:workspace_id>/history/", views.tool_history, name="history"),
    # Groups (admin only)
    path("<uuid:workspace_id>/groups/", views.group_list, name="group_list"),
    path("<uuid:workspace_id>/groups/create/", views.group_create, name="group_create"),
    path("<uuid:workspace_id>/groups/<uuid:group_id>/", views.group_manage, name="group_manage"),
    path("<uuid:workspace_id>/groups/<uuid:group_id>/edit/", views.group_edit, name="group_edit"),
    path("<uuid:workspace_id>/groups/<uuid:group_id>/delete/", views.group_delete, name="group_delete"),
    path("<uuid:workspace_id>/groups/<uuid:group_id>/grant/", views.group_grant, name="group_grant"),
    path("<uuid:workspace_id>/groups/<uuid:group_id>/revoke/", views.group_revoke, name="group_revoke"),
    path("<uuid:workspace_id>/<uuid:tool_id>/assign-group/", views.tool_assign_group, name="tool_assign_group"),
    path("<uuid:workspace_id>/<uuid:tool_id>/launch/", views.tool_launch, name="launch"),
    path("<uuid:workspace_id>/<uuid:tool_id>/return/", views.tool_return, name="return"),
    path("<uuid:workspace_id>/<uuid:tool_id>/force-return/", views.tool_force_return, name="force_return"),
    path("<uuid:workspace_id>/<uuid:tool_id>/update-cookies/", views.tool_update_cookies, name="update_cookies"),
    path("<uuid:workspace_id>/<uuid:tool_id>/delete/", views.tool_delete, name="delete"),
]

from django.contrib import admin

from .tracking.models import ParentChildAccess


@admin.register(ParentChildAccess)
class ParentChildAccessAdmin(admin.ModelAdmin):
    list_display = ["user", "student"]
    list_select_related = ["user", "student"]
    search_fields = ["user__username", "student__name"]

from django.contrib import admin

from .models import Abonnement, Categorie, Cours, Mois, OptionAbonnement


@admin.register(Categorie)
class CategorieAdmin(admin.ModelAdmin):
    list_display = ("nom",)
    search_fields = ("nom",)


@admin.register(Mois)
class MoisAdmin(admin.ModelAdmin):
    list_display = ("nom", "ordre")
    search_fields = ("nom",)
    ordering = ("ordre",)


@admin.register(Cours)
class CoursAdmin(admin.ModelAdmin):
    list_display = ("titre", "categorie", "mois", "cree_le")
    list_filter = ("categorie", "mois")
    search_fields = ("titre", "description")


@admin.register(Abonnement)
class AbonnementAdmin(admin.ModelAdmin):
    list_display = ("candidat", "categorie", "mois", "option", "montant", "statut", "date_abonnement")
    list_filter = ("categorie", "mois", "option__type_abonnement", "statut")
    search_fields = ("candidat__username", "candidat__first_name")


@admin.register(OptionAbonnement)
class OptionAbonnementAdmin(admin.ModelAdmin):
    list_display = ("type_abonnement", "montant", "actif", "mis_a_jour_le")
    list_filter = ("type_abonnement", "actif")
    search_fields = ("type_abonnement",)

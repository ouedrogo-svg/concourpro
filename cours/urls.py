from django.urls import path

from .views import (
    changer_mot_de_passe,
    connexion_candidat,
    creer_categorie,
    creer_cours,
    creer_mois,
    deconnexion_candidat,
    espace_candidats,
    inscription_candidat,
    liste_cours,
    profil_candidat,
)

urlpatterns = [
    path("", liste_cours, name="liste_cours"),
    path("candidats/inscription/", inscription_candidat, name="inscription_candidat"),
    path("candidats/connexion/", connexion_candidat, name="connexion_candidat"),
    path("candidats/deconnexion/", deconnexion_candidat, name="deconnexion_candidat"),
    path("candidats/profil/", profil_candidat, name="profil_candidat"),
    path("candidats/mot-de-passe/", changer_mot_de_passe, name="changer_mot_de_passe"),
    path("candidats/", espace_candidats, name="espace_candidats"),
    path("categories/nouveau/", creer_categorie, name="creer_categorie"),
    path("mois/nouveau/", creer_mois, name="creer_mois"),
    path("cours/nouveau/", creer_cours, name="creer_cours"),
]

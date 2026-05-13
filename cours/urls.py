from django.urls import path

from .views import (
    abonnements_formateur,
    espace_formateur,
    changer_mot_de_passe,
    connexion_candidat,
    creer_categorie,
    creer_correction,
    creer_cours,
    creer_mois,
    deconnexion_candidat,
    espace_candidats,
    inscription_candidat,
    liste_cours,
    profil_candidat,
    quiz_correction,
    support_pdf_cours,
    support_pdf_correction,
)

urlpatterns = [
    path("", espace_candidats, name="racine"),
    path("accueil/", liste_cours, name="liste_cours"),
    path("candidats/inscription/", inscription_candidat, name="inscription_candidat"),
    path("candidats/connexion/", connexion_candidat, name="connexion_candidat"),
    path("candidats/deconnexion/", deconnexion_candidat, name="deconnexion_candidat"),
    path("candidats/profil/", profil_candidat, name="profil_candidat"),
    path("candidats/mot-de-passe/", changer_mot_de_passe, name="changer_mot_de_passe"),
    path(
        "candidats/cours/<int:cours_id>/support-pdf/",
        support_pdf_cours,
        name="support_pdf_cours",
    ),
    path(
        "candidats/corrections/<int:correction_id>/support-pdf/",
        support_pdf_correction,
        name="support_pdf_correction",
    ),
    path(
        "candidats/corrections/<int:correction_id>/quiz/",
        quiz_correction,
        name="quiz_correction",
    ),
    path("candidats/", espace_candidats, name="espace_candidats"),
    path("formateur/", espace_formateur, name="espace_formateur"),
    path(
        "formateur/abonnements/",
        abonnements_formateur,
        name="abonnements_formateur",
    ),
    path("categories/nouveau/", creer_categorie, name="creer_categorie"),
    path("mois/nouveau/", creer_mois, name="creer_mois"),
    path("cours/nouveau/", creer_cours, name="creer_cours"),
    path("corrections/nouveau/", creer_correction, name="creer_correction"),
]

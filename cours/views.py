import os
from functools import wraps

from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Case, IntegerField, Value, When
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render

from .forms import (
    ChangerMotDePasseForm,
    CategorieForm,
    ConnexionCandidatForm,
    CoursForm,
    InscriptionCandidatForm,
    MoisForm,
)
from .models import Abonnement, Categorie, Cours, Mois, OptionAbonnement


def candidat_a_acces_au_cours(user, cours: Cours) -> bool:
    """Meme regles que l'espace candidat : abonnement annuel ou mensuel valide."""
    if user.is_staff:
        return True
    annuel = Abonnement.objects.filter(
        candidat=user,
        categorie_id=cours.categorie_id,
        option__type_abonnement=OptionAbonnement.TYPE_ANNUEL,
        statut=Abonnement.STATUT_VALIDE,
    ).exists()
    if annuel:
        return True
    return Abonnement.objects.filter(
        candidat=user,
        categorie_id=cours.categorie_id,
        mois_id=cours.mois_id,
        option__type_abonnement=OptionAbonnement.TYPE_MENSUEL,
        statut=Abonnement.STATUT_VALIDE,
    ).exists()


def exiger_formateur(view_func):
    """Connexion obligatoire + compte staff (formateur)."""

    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_staff:
            raise PermissionDenied
        return view_func(request, *args, **kwargs)

    return login_required(login_url="connexion_candidat")(_wrapped)


def liste_cours(request):
    categorie_id = request.GET.get("categorie")
    mois_id = request.GET.get("mois")

    cours_queryset = Cours.objects.select_related("categorie", "mois").all()

    if categorie_id:
        cours_queryset = cours_queryset.filter(categorie_id=categorie_id)
    if mois_id:
        cours_queryset = cours_queryset.filter(mois_id=mois_id)

    context = {
        "cours_list": cours_queryset.order_by("categorie__nom", "mois__ordre", "titre"),
        "categories": Categorie.objects.all(),
        "mois_list": Mois.objects.all(),
        "selected_categorie": categorie_id or "",
        "selected_mois": mois_id or "",
    }
    return render(request, "cours/liste_cours.html", context)


@exiger_formateur
def creer_categorie(request):
    if request.method == "POST":
        form = CategorieForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Categorie creee avec succes.")
            return redirect("espace_formateur")
    else:
        form = CategorieForm()

    return render(request, "cours/formulaire_categorie.html", {"form": form})


@exiger_formateur
def creer_mois(request):
    if request.method == "POST":
        form = MoisForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Mois cree avec succes.")
            return redirect("espace_formateur")
    else:
        form = MoisForm()

    return render(request, "cours/formulaire_mois.html", {"form": form})


@exiger_formateur
def creer_cours(request):
    if request.method == "POST":
        form = CoursForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            messages.success(request, "Cours cree avec succes.")
            return redirect("espace_formateur")
    else:
        form = CoursForm()

    return render(request, "cours/formulaire_cours.html", {"form": form})


def inscription_candidat(request):
    if request.user.is_authenticated:
        return redirect("espace_candidats")

    if request.method == "POST":
        form = InscriptionCandidatForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, "Inscription reussie. Bienvenue dans votre espace candidat.")
            return redirect("espace_candidats")
    else:
        form = InscriptionCandidatForm()

    return render(request, "cours/inscription_candidat.html", {"form": form})


def connexion_candidat(request):
    if request.user.is_authenticated:
        if request.user.is_staff:
            return redirect("espace_formateur")
        return redirect("espace_candidats")

    if request.method == "POST":
        form = ConnexionCandidatForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            messages.success(request, "Connexion reussie.")
            if user.is_staff:
                return redirect("espace_formateur")
            return redirect("espace_candidats")
    else:
        form = ConnexionCandidatForm(request)

    return render(request, "cours/connexion_candidat.html", {"form": form})


def deconnexion_candidat(request):
    logout(request)
    messages.success(request, "Vous etes deconnecte.")
    return redirect("connexion_candidat")


@login_required(login_url="connexion_candidat")
def profil_candidat(request):
    return render(request, "cours/profil_candidat.html")


@login_required(login_url="connexion_candidat")
def changer_mot_de_passe(request):
    if request.method == "POST":
        form = ChangerMotDePasseForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)
            messages.success(request, "Mot de passe modifie avec succes.")
            return redirect("profil_candidat")
    else:
        form = ChangerMotDePasseForm(request.user)

    return render(request, "cours/changer_mot_de_passe.html", {"form": form})


@login_required(login_url="connexion_candidat")
def support_pdf_cours(request, cours_id):
    """
    Sert le PDF via Django (fonctionne sans exposition directe de /media/ en production).
    Acces reserve aux candidats avec abonnement valide (memes regles que la liste des cours).
    """
    cours = get_object_or_404(
        Cours.objects.select_related("categorie", "mois"), pk=cours_id
    )
    if not candidat_a_acces_au_cours(request.user, cours):
        raise PermissionDenied
    if not cours.fichier_pdf or not cours.fichier_pdf.name:
        raise Http404("Aucun fichier PDF pour ce cours.")
    try:
        fichier = cours.fichier_pdf.open("rb")
    except (FileNotFoundError, OSError, ValueError):
        raise Http404("Le fichier PDF est introuvable sur le serveur.")
    nom_fichier = os.path.basename(cours.fichier_pdf.name) or "support.pdf"
    return FileResponse(
        fichier,
        as_attachment=False,
        filename=nom_fichier,
        content_type="application/pdf",
    )


@login_required(login_url="connexion_candidat")
def espace_candidats(request):
    options = OptionAbonnement.objects.filter(actif=True).order_by("type_abonnement")
    mes_abonnements = (
        Abonnement.objects.select_related("categorie", "mois", "option")
        .filter(candidat=request.user)
        .annotate(
            statut_ordre=Case(
                When(statut=Abonnement.STATUT_EN_ATTENTE, then=Value(0)),
                When(statut=Abonnement.STATUT_VALIDE, then=Value(1)),
                When(statut=Abonnement.STATUT_REJETE, then=Value(2)),
                default=Value(3),
                output_field=IntegerField(),
            )
        )
        .order_by("statut_ordre", "-date_abonnement")
    )

    if request.method == "POST":
        categorie_id = request.POST.get("categorie")
        mois_id = request.POST.get("mois")
        option_id = request.POST.get("option")
        if categorie_id and option_id:
            option = OptionAbonnement.objects.filter(id=option_id, actif=True).first()
            if not option:
                messages.error(request, "Option d'abonnement invalide.")
                return redirect("espace_candidats")

            if option.type_abonnement == OptionAbonnement.TYPE_MENSUEL and not mois_id:
                messages.error(
                    request, "Veuillez selectionner un mois pour un abonnement mensuel."
                )
                return redirect(f"{request.path}?categorie={categorie_id}")

            abonnement, cree = Abonnement.objects.get_or_create(
                candidat=request.user,
                categorie_id=categorie_id,
                mois_id=mois_id if option.type_abonnement == OptionAbonnement.TYPE_MENSUEL else None,
                option=option,
                defaults={
                    "montant": option.montant,
                    "statut": Abonnement.STATUT_EN_ATTENTE,
                },
            )
            if cree:
                messages.success(
                    request,
                    "Demande d'abonnement enregistree. Vous aurez acces aux cours apres validation par le formateur.",
                )
            else:
                messages.info(
                    request,
                    f"Vous avez deja un abonnement {abonnement.get_statut_display().lower()} pour cette selection.",
                )

            redirection = f"{request.path}?categorie={categorie_id}"
            if mois_id:
                redirection += f"&mois={mois_id}"
            return redirect(redirection)

    categorie_id = request.GET.get("categorie")
    mois_id = request.GET.get("mois")
    selected_categorie_obj = None
    selected_mois_obj = None
    abonnement_actif = False
    cours_queryset = Cours.objects.none()
    message_abonnement = ""

    if categorie_id:
        selected_categorie_obj = Categorie.objects.filter(id=categorie_id).first()
    if mois_id:
        selected_mois_obj = Mois.objects.filter(id=mois_id).first()

    abonnement_annuel_valide = None
    abonnement_mensuel_valide = None
    abonnement_en_attente = None

    if categorie_id:
        abonnement_annuel_valide = (
            Abonnement.objects.select_related("option")
            .filter(
                candidat=request.user,
                categorie_id=categorie_id,
                option__type_abonnement=OptionAbonnement.TYPE_ANNUEL,
                statut=Abonnement.STATUT_VALIDE,
            )
            .first()
        )
        if mois_id:
            abonnement_mensuel_valide = (
                Abonnement.objects.select_related("option")
                .filter(
                    candidat=request.user,
                    categorie_id=categorie_id,
                    mois_id=mois_id,
                    option__type_abonnement=OptionAbonnement.TYPE_MENSUEL,
                    statut=Abonnement.STATUT_VALIDE,
                )
                .first()
            )

        abonnement_en_attente = (
            Abonnement.objects.select_related("option")
            .filter(
                candidat=request.user,
                categorie_id=categorie_id,
                statut=Abonnement.STATUT_EN_ATTENTE,
            )
            .first()
        )

        if abonnement_annuel_valide:
            abonnement_actif = True
            # Abonnement annuel : acces a tous les cours de la categorie, tous les mois.
            cours_queryset = Cours.objects.select_related("categorie", "mois").filter(
                categorie_id=categorie_id
            )
        elif mois_id and abonnement_mensuel_valide:
            abonnement_actif = True
            cours_queryset = Cours.objects.select_related("categorie", "mois").filter(
                categorie_id=categorie_id, mois_id=mois_id
            )
        elif abonnement_en_attente:
            message_abonnement = (
                "Votre abonnement est en attente de validation par le formateur."
            )
        else:
            message_abonnement = (
                "Vous devez souscrire un abonnement puis attendre sa validation "
                "pour acceder aux cours."
            )
    else:
        message_abonnement = (
            "Selectionnez une categorie, puis choisissez une option d'abonnement."
        )

    context = {
        "categories": Categorie.objects.all(),
        "mois_list": Mois.objects.all(),
        "options_abonnement": options,
        "mes_abonnements": mes_abonnements,
        "cours_list": cours_queryset.order_by("mois__ordre", "titre"),
        "selected_categorie": categorie_id or "",
        "selected_mois": mois_id or "",
        "selected_categorie_obj": selected_categorie_obj,
        "selected_mois_obj": selected_mois_obj,
        "abonnement_actif": abonnement_actif,
        "message_abonnement": message_abonnement,
        "abonnement_annuel_valide": abonnement_annuel_valide,
    }
    return render(request, "cours/espace_candidats.html", context)


@exiger_formateur
def espace_formateur(request):
    """Tableau de bord : contenu pedagogique et validation des abonnements."""
    nb_attente = Abonnement.objects.filter(
        statut=Abonnement.STATUT_EN_ATTENTE
    ).count()
    return render(
        request,
        "cours/espace_formateur.html",
        {
            "nb_abonnements_attente": nb_attente,
            "nb_categories": Categorie.objects.count(),
            "nb_mois": Mois.objects.count(),
            "nb_cours": Cours.objects.count(),
        },
    )


@exiger_formateur
def abonnements_formateur(request):
    """Validation des abonnements par un compte formateur (is_staff)."""
    if request.method == "POST":
        abonnement_id = request.POST.get("abonnement_id")
        action = request.POST.get("action")
        abonnement = get_object_or_404(Abonnement, pk=abonnement_id)
        if action == "valider":
            abonnement.statut = Abonnement.STATUT_VALIDE
            abonnement.save(update_fields=["statut"])
            messages.success(
                request,
                f"Abonnement valide pour {abonnement.candidat.get_username()} — "
                f"{abonnement.categorie.nom}.",
            )
        elif action == "rejeter":
            abonnement.statut = Abonnement.STATUT_REJETE
            abonnement.save(update_fields=["statut"])
            messages.info(
                request,
                f"Abonnement refuse pour {abonnement.candidat.get_username()} — "
                f"{abonnement.categorie.nom}.",
            )
        else:
            messages.error(request, "Action non reconnue.")
        return redirect("abonnements_formateur")

    en_attente = (
        Abonnement.objects.select_related(
            "candidat", "categorie", "mois", "option"
        )
        .filter(statut=Abonnement.STATUT_EN_ATTENTE)
        .order_by("date_abonnement")
    )
    recents = (
        Abonnement.objects.select_related(
            "candidat", "categorie", "mois", "option"
        )
        .exclude(statut=Abonnement.STATUT_EN_ATTENTE)
        .order_by("-date_abonnement")[:30]
    )
    return render(
        request,
        "cours/abonnements_formateur.html",
        {"en_attente": en_attente, "recents": recents},
    )

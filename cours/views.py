from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth import update_session_auth_hash
from django.db.models import Case, IntegerField, Value, When
from django.shortcuts import redirect, render

from .forms import (
    ChangerMotDePasseForm,
    CategorieForm,
    ConnexionCandidatForm,
    CoursForm,
    InscriptionCandidatForm,
    MoisForm,
)
from .models import Abonnement, Categorie, Cours, Mois, OptionAbonnement


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


def creer_categorie(request):
    if request.method == "POST":
        form = CategorieForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Categorie creee avec succes.")
            return redirect("liste_cours")
    else:
        form = CategorieForm()

    return render(request, "cours/formulaire_categorie.html", {"form": form})


def creer_mois(request):
    if request.method == "POST":
        form = MoisForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Mois cree avec succes.")
            return redirect("liste_cours")
    else:
        form = MoisForm()

    return render(request, "cours/formulaire_mois.html", {"form": form})


def creer_cours(request):
    if request.method == "POST":
        form = CoursForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            messages.success(request, "Cours cree avec succes.")
            return redirect("liste_cours")
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
        return redirect("espace_candidats")

    if request.method == "POST":
        form = ConnexionCandidatForm(request, data=request.POST)
        if form.is_valid():
            login(request, form.get_user())
            messages.success(request, "Connexion reussie.")
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
            cours_queryset = Cours.objects.select_related("categorie", "mois").filter(
                categorie_id=categorie_id
            )
            if mois_id:
                cours_queryset = cours_queryset.filter(mois_id=mois_id)
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
    }
    return render(request, "cours/espace_candidats.html", context)

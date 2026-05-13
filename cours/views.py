import os
import re
from functools import wraps

from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Case, IntegerField, Value, When
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.clickjacking import xframe_options_sameorigin

from .forms import (
    ChangerMotDePasseForm,
    CategorieForm,
    ConnexionCandidatForm,
    CorrectionForm,
    CoursForm,
    InscriptionCandidatForm,
    MoisForm,
)
from .models import (
    Abonnement,
    Categorie,
    Correction,
    CorrectionQuizItem,
    Cours,
    Mois,
    OptionAbonnement,
)
from .pdf_quiz import extract_quiz_rows_from_pdf


def _correction_pdf_abs_path(correction: Correction) -> str | None:
    """Chemin local du PDF (FileSystemStorage) ; None si fichier absent ou stockage distant."""
    f = correction.fichier_pdf
    if not f:
        return None
    name = (getattr(f, "name", None) or "").strip()
    if not name:
        return None
    p: str | None = None
    try:
        p = f.path
    except (ValueError, AttributeError):
        p = None
    if p and os.path.isfile(p):
        return p
    storage = f.storage
    if hasattr(storage, "path"):
        try:
            p2 = storage.path(name)
            if os.path.isfile(p2):
                return p2
        except OSError:
            pass
    return None


def _propositions_to_json(props: tuple) -> list:
    return [{"lettre": L, "texte": t} for L, t in props]


def _allowed_letters_for_item(item: CorrectionQuizItem) -> set[str]:
    letters: set[str] = set()
    p = item.propositions_json
    if isinstance(p, list):
        for d in p:
            if not isinstance(d, dict):
                continue
            L = str(d.get("lettre", "")).strip().lower()
            if len(L) == 1 and "a" <= L <= "z":
                letters.add(L)
    for c in (item.bonne_reponse or "").upper():
        if "A" <= c <= "Z":
            letters.add(c.lower())
    if letters:
        return letters
    return set("abcd")


def _propositions_for_template(item: CorrectionQuizItem) -> list[dict]:
    p = item.propositions_json
    if isinstance(p, list) and p:
        out: list[dict] = []
        for d in p:
            if not isinstance(d, dict):
                continue
            L = str(d.get("lettre", "")).strip().upper()
            if len(L) != 1 or not ("A" <= L <= "Z"):
                continue
            out.append({"lettre": L, "texte": str(d.get("texte", "")).strip()})
        if out:
            return out
    allowed = _allowed_letters_for_item(item)
    letters = [L for L in "ABCDEFGHIJKLMNOPQRSTUVWXYZ" if L.lower() in allowed]
    out = [{"lettre": L, "texte": ""} for L in letters]
    if not out:
        return [{"lettre": L, "texte": ""} for L in "ABCD"]
    return out


def _refresh_quiz_items_from_pdf(correction: Correction, items: list) -> list:
    """
    Met a jour questions / reponses / propositions depuis le PDF (memes ids).
    Ne supprime jamais de lignes : si le PDF a plus ou moins de lignes que la base,
    seuls les premiers elements (par ordre) sont alignes.
    """
    if not items:
        return items
    path = _correction_pdf_abs_path(correction)
    if not path:
        return items
    try:
        rows, _ = extract_quiz_rows_from_pdf(path)
    except Exception:
        return items
    if not rows:
        return items
    ordered = sorted(items, key=lambda x: (x.ordre, x.id))
    for it, r in zip(ordered, rows):
        plist = _propositions_to_json(r.propositions)
        CorrectionQuizItem.objects.filter(pk=it.pk).update(
            question=r.question,
            bonne_reponse=r.reponse,
            propositions_json=plist,
        )
        it.question = r.question
        it.bonne_reponse = r.reponse
        it.propositions_json = plist
    return items


def _pdf_mtime_token(correction: Correction) -> str:
    p = _correction_pdf_abs_path(correction)
    if not p:
        return "0"
    try:
        return str(int(os.path.getmtime(p)))
    except OSError:
        return "0"


def _display_quiz_question(text: str) -> str:
    """Retire le bloc de reference type 'NB : Article...' pour l'affichage."""
    if not text:
        return ""
    parts = re.split(r"(?i)\n\s*NB\s*:", text, maxsplit=1)
    return parts[0].strip()


def _normalize_quiz_selection(s: str, allowed: set[str]) -> str:
    """Ensemble de lettres, trie (ex. candidat), en filtrant par lettres autorisees."""
    letters = [c.lower() for c in (s or "") if c.lower() in allowed]
    return "".join(sorted(set(letters)))


def _quiz_expected_normalized(bonne: str, allowed: set[str]) -> str:
    """
    Extrait la combinaison attendue (ex. AB, C) depuis la cellule reponse du PDF.
    Evite de prendre toutes les lettres d'une phrase en francais.
    """
    raw = (bonne or "").strip().upper()
    compact = re.sub(r"[\s,;]+", "", raw)
    if re.fullmatch(r"[A-Z]{1,8}", compact):
        inner = [c.lower() for c in compact if c.lower() in allowed]
        if inner:
            return "".join(sorted(set(inner)))
    for tok in reversed(re.findall(r"[A-Z]{1,8}", raw)):
        if not re.fullmatch(r"[A-Z]+", tok) or len(tok) > 8:
            continue
        inner = [c.lower() for c in tok if c.lower() in allowed]
        if len(inner) == len(tok):
            return "".join(sorted(set(inner)))
    return _normalize_quiz_selection(bonne, allowed)


def _letters_from_post(raw_list: list, allowed: set[str]) -> str:
    out: list[str] = []
    for v in raw_list:
        c = (v or "").strip().lower()
        if len(c) == 1 and c in allowed:
            out.append(c)
    return "".join(sorted(set(out)))


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


def candidat_a_acces(user, categorie_id: int, mois_id: int) -> bool:
    if user.is_staff:
        return True
    annuel = Abonnement.objects.filter(
        candidat=user,
        categorie_id=categorie_id,
        option__type_abonnement=OptionAbonnement.TYPE_ANNUEL,
        statut=Abonnement.STATUT_VALIDE,
    ).exists()
    if annuel:
        return True
    return Abonnement.objects.filter(
        candidat=user,
        categorie_id=categorie_id,
        mois_id=mois_id,
        option__type_abonnement=OptionAbonnement.TYPE_MENSUEL,
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
        if not request.user.is_authenticated:
            return redirect("connexion_candidat")
        if not request.user.is_staff:
            messages.error(
                request,
                "Acces refuse: connectez-vous avec un compte formateur.",
            )
            return redirect("espace_candidats")
        return view_func(request, *args, **kwargs)

    return _wrapped


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


@exiger_formateur
def creer_correction(request):
    if request.method == "POST":
        form = CorrectionForm(request.POST, request.FILES)
        if form.is_valid():
            correction = form.save()
            rows = []
            warnings = []
            try:
                pdf_path = _correction_pdf_abs_path(correction)
                if pdf_path:
                    rows, warnings = extract_quiz_rows_from_pdf(pdf_path)
                else:
                    warnings = ["Fichier PDF introuvable sur le disque."]
            except Exception as e:
                warnings = [f"Extraction du quiz impossible: {e}"]

            if rows:
                CorrectionQuizItem.objects.filter(correction=correction).delete()
                items = [
                    CorrectionQuizItem(
                        correction=correction,
                        ordre=i + 1,
                        question=r.question,
                        bonne_reponse=r.reponse,
                        propositions_json=_propositions_to_json(r.propositions),
                    )
                    for i, r in enumerate(rows)
                ]
                CorrectionQuizItem.objects.bulk_create(items)
                messages.success(
                    request,
                    f"Correction creee avec succes. {len(rows)} question(s) de quiz extraite(s).",
                )
            else:
                messages.success(request, "Correction creee avec succes.")
                for w in warnings:
                    messages.warning(request, w)
            return redirect("espace_formateur")
    else:
        form = CorrectionForm()

    return render(request, "cours/formulaire_correction.html", {"form": form})


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
@xframe_options_sameorigin
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
@xframe_options_sameorigin
def support_pdf_correction(request, correction_id):
    correction = get_object_or_404(
        Correction.objects.select_related("categorie", "mois"), pk=correction_id
    )
    if not candidat_a_acces(request.user, correction.categorie_id, correction.mois_id):
        raise PermissionDenied
    if not correction.fichier_pdf or not correction.fichier_pdf.name:
        raise Http404("Aucun fichier PDF pour cette correction.")
    try:
        fichier = correction.fichier_pdf.open("rb")
    except (FileNotFoundError, OSError, ValueError):
        raise Http404("Le fichier PDF est introuvable sur le serveur.")
    nom_fichier = os.path.basename(correction.fichier_pdf.name) or "correction.pdf"
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
    corrections_queryset = Correction.objects.none()
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
            corrections_queryset = Correction.objects.select_related(
                "categorie", "mois"
            ).filter(categorie_id=categorie_id)
        elif mois_id and abonnement_mensuel_valide:
            abonnement_actif = True
            cours_queryset = Cours.objects.select_related("categorie", "mois").filter(
                categorie_id=categorie_id, mois_id=mois_id
            )
            corrections_queryset = Correction.objects.select_related(
                "categorie", "mois"
            ).filter(categorie_id=categorie_id, mois_id=mois_id)
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
        "corrections_list": corrections_queryset.order_by("mois__ordre", "titre"),
        "selected_categorie": categorie_id or "",
        "selected_mois": mois_id or "",
        "selected_categorie_obj": selected_categorie_obj,
        "selected_mois_obj": selected_mois_obj,
        "abonnement_actif": abonnement_actif,
        "message_abonnement": message_abonnement,
        "abonnement_annuel_valide": abonnement_annuel_valide,
    }
    return render(request, "cours/espace_candidats.html", context)


@login_required(login_url="connexion_candidat")
def quiz_correction(request, correction_id: int):
    correction = get_object_or_404(
        Correction.objects.select_related("categorie", "mois"), pk=correction_id
    )
    if not candidat_a_acces(request.user, correction.categorie_id, correction.mois_id):
        raise PermissionDenied

    items = list(
        CorrectionQuizItem.objects.filter(correction=correction).order_by("ordre", "id")
    )

    if not items:
        # Compatibilite: anciennes corrections creees avant le quiz auto.
        pdf_path = _correction_pdf_abs_path(correction)
        rows: list = []
        extract_warnings: list[str] = []
        if not pdf_path:
            messages.error(
                request,
                "Le fichier PDF de cette correction est introuvable sur le serveur "
                "(aucune piece jointe ou fichier deplace).",
            )
        else:
            try:
                rows, extract_warnings = extract_quiz_rows_from_pdf(pdf_path)
            except Exception as exc:
                messages.error(
                    request,
                    f"Erreur lors de la lecture du PDF : {exc}",
                )
                rows = []
            for w in extract_warnings[:2]:
                if w:
                    messages.warning(request, w)
        if rows:
            try:
                with transaction.atomic():
                    CorrectionQuizItem.objects.filter(correction=correction).delete()
                    CorrectionQuizItem.objects.bulk_create(
                        [
                            CorrectionQuizItem(
                                correction=correction,
                                ordre=i + 1,
                                question=r.question,
                                bonne_reponse=r.reponse,
                                propositions_json=_propositions_to_json(r.propositions),
                            )
                            for i, r in enumerate(rows)
                        ]
                    )
            except Exception as exc:
                messages.error(
                    request,
                    f"Impossible d'enregistrer les questions extraites : {exc}",
                )
            else:
                items = list(
                    CorrectionQuizItem.objects.filter(correction=correction).order_by(
                        "ordre", "id"
                    )
                )

    if not items:
        messages.info(
            request,
            "Aucune question n'a pu etre extraite du PDF pour ce quiz interactif. "
            "Verifiez que le PDF contient bien un tableau Questions / Reponses, "
            "ou reessayez apres mise a jour du fichier. Vous pouvez aussi consulter le document source.",
        )
        return render(
            request,
            "cours/quiz_correction.html",
            {
                "correction": correction,
                "items": [],
                "question_rows": [],
                "resultats": None,
                "quiz_unavailable": True,
            },
        )

    # Synchro PDF : une fois par version du fichier (mtime), ou si ?sync=1
    if request.method == "GET":
        sk = f"quiz_pdf_{correction.id}"
        token = _pdf_mtime_token(correction)
        if request.GET.get("sync") == "1" or request.session.get(sk) != token:
            try:
                items = _refresh_quiz_items_from_pdf(correction, items)
                request.session[sk] = token
            except Exception:
                pass

    resultats = None
    if request.method == "POST":
        bonnes = 0
        details = []
        for it in items:
            key = f"q_{it.id}"
            raw = request.POST.getlist(key)
            allowed_cf = _allowed_letters_for_item(it)
            candidat_norm = _letters_from_post(raw, allowed_cf)
            attendu_norm = _quiz_expected_normalized(it.bonne_reponse or "", allowed_cf)
            ok = candidat_norm == attendu_norm
            if ok:
                bonnes += 1
            lettres_cochees = [c.upper() for c in candidat_norm]
            details.append(
                {
                    "item": it,
                    "reponse_candidat": "".join(lettres_cochees) or "—",
                    "lettres_cochees": lettres_cochees,
                    "ok": ok,
                }
            )
        total = len(items)
        score = round((bonnes / total) * 100, 2) if total else 0
        resultats = {"bonnes": bonnes, "total": total, "score": score, "details": details}

    question_rows = [
        {
            "item": it,
            "propositions": _propositions_for_template(it),
            "question_display": _display_quiz_question(it.question),
        }
        for it in items
    ]

    return render(
        request,
        "cours/quiz_correction.html",
        {
            "correction": correction,
            "items": items,
            "question_rows": question_rows,
            "resultats": resultats,
            "quiz_unavailable": False,
        },
    )


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
            "nb_corrections": Correction.objects.count(),
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

from django.db import models
from django.conf import settings


class Categorie(models.Model):
    nom = models.CharField(max_length=120, unique=True)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["nom"]
        verbose_name = "Categorie"
        verbose_name_plural = "Categories"

    def __str__(self):
        return self.nom


class Mois(models.Model):
    nom = models.CharField(max_length=40, unique=True)
    ordre = models.PositiveSmallIntegerField()

    class Meta:
        ordering = ["ordre", "nom"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(ordre__gte=1) & models.Q(ordre__lte=12),
                name="mois_ordre_entre_1_et_12",
            )
        ]
        verbose_name = "Mois"
        verbose_name_plural = "Mois"

    def __str__(self):
        return self.nom


class Cours(models.Model):
    titre = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    categorie = models.ForeignKey(
        Categorie, on_delete=models.CASCADE, related_name="cours"
    )
    mois = models.ForeignKey(Mois, on_delete=models.PROTECT, related_name="cours")
    fichier_pdf = models.FileField(upload_to="cours_pdfs/")
    cree_le = models.DateTimeField(auto_now_add=True)
    mis_a_jour_le = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-cree_le"]
        verbose_name = "Cours"
        verbose_name_plural = "Cours"

    def __str__(self):
        return self.titre


class Correction(models.Model):
    titre = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    categorie = models.ForeignKey(
        Categorie, on_delete=models.CASCADE, related_name="corrections"
    )
    mois = models.ForeignKey(Mois, on_delete=models.PROTECT, related_name="corrections")
    fichier_pdf = models.FileField(upload_to="corrections_pdfs/")
    cree_le = models.DateTimeField(auto_now_add=True)
    mis_a_jour_le = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-cree_le"]
        verbose_name = "Correction"
        verbose_name_plural = "Corrections"

    def __str__(self):
        return self.titre


class CorrectionQuizItem(models.Model):
    """
    Une ligne du quiz extraite du PDF de correction.
    La "bonne reponse" correspond a la colonne `reponses` du PDF.
    Les propositions (texte des choix A, B, C...) viennent des colonnes
    correspondantes du meme tableau PDF.
    """

    correction = models.ForeignKey(
        Correction, on_delete=models.CASCADE, related_name="quiz_items"
    )
    ordre = models.PositiveIntegerField(default=1)
    question = models.TextField()
    bonne_reponse = models.TextField()
    propositions_json = models.JSONField(
        default=list,
        blank=True,
    )

    class Meta:
        ordering = ["ordre", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["correction", "ordre"],
                name="correction_quiz_item_unique_ordre",
            )
        ]
        verbose_name = "Question de quiz (correction)"
        verbose_name_plural = "Questions de quiz (corrections)"

    def __str__(self):
        return f"{self.correction.titre} — Q{self.ordre}"


class OptionAbonnement(models.Model):
    TYPE_MENSUEL = "mensuel"
    TYPE_ANNUEL = "annuel"
    TYPE_CHOICES = (
        (TYPE_MENSUEL, "Mensuel"),
        (TYPE_ANNUEL, "Annuel"),
    )

    type_abonnement = models.CharField(max_length=20, choices=TYPE_CHOICES, unique=True)
    montant = models.DecimalField(max_digits=10, decimal_places=2)
    actif = models.BooleanField(default=True)
    cree_le = models.DateTimeField(auto_now_add=True)
    mis_a_jour_le = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["type_abonnement"]
        verbose_name = "Option d'abonnement"
        verbose_name_plural = "Options d'abonnement"

    def __str__(self):
        return f"{self.get_type_abonnement_display()} - {self.montant}"


class Abonnement(models.Model):
    STATUT_EN_ATTENTE = "en_attente"
    STATUT_VALIDE = "valide"
    STATUT_REJETE = "rejete"
    STATUT_CHOICES = (
        (STATUT_EN_ATTENTE, "En attente"),
        (STATUT_VALIDE, "Valide"),
        (STATUT_REJETE, "Rejete"),
    )

    candidat = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="abonnements"
    )
    categorie = models.ForeignKey(
        Categorie, on_delete=models.CASCADE, related_name="abonnements"
    )
    mois = models.ForeignKey(
        Mois, on_delete=models.CASCADE, related_name="abonnements", null=True, blank=True
    )
    option = models.ForeignKey(
        OptionAbonnement,
        on_delete=models.PROTECT,
        related_name="abonnements",
        null=True,
        blank=True,
    )
    montant = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    statut = models.CharField(
        max_length=20, choices=STATUT_CHOICES, default=STATUT_EN_ATTENTE
    )
    date_abonnement = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date_abonnement"]
        constraints = [
            models.UniqueConstraint(
                fields=["candidat", "categorie", "mois", "option"],
                name="abonnement_unique_candidat_categorie_mois_option",
            )
        ]
        verbose_name = "Abonnement"
        verbose_name_plural = "Abonnements"

    def __str__(self):
        mois_label = self.mois.nom if self.mois else "Tous les mois"
        option_label = (
            self.option.get_type_abonnement_display()
            if self.option
            else "Option non definie"
        )
        return (
            f"{self.candidat.username} - {self.categorie.nom} - {mois_label} - "
            f"{option_label} ({self.get_statut_display()})"
        )

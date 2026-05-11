import shutil
import tempfile

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import Abonnement, Categorie, Cours, Mois


TEST_MEDIA_ROOT = tempfile.mkdtemp()


@override_settings(MEDIA_ROOT=TEST_MEDIA_ROOT)
class CoursAppTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEST_MEDIA_ROOT, ignore_errors=True)

    def setUp(self):
        self.categorie_a = Categorie.objects.create(nom="Programmation", description="Dev")
        self.categorie_b = Categorie.objects.create(nom="Design", description="UI")
        self.mois_janvier = Mois.objects.create(nom="Janvier", ordre=1)
        self.mois_fevrier = Mois.objects.create(nom="Fevrier", ordre=2)

    def _pdf(self, name="cours.pdf"):
        return SimpleUploadedFile(
            name=name,
            content=b"%PDF-1.4\n%test\n",
            content_type="application/pdf",
        )

    def test_pages_accessibles(self):
        self.assertEqual(self.client.get(reverse("liste_cours")).status_code, 200)
        self.assertEqual(self.client.get(reverse("inscription_candidat")).status_code, 200)
        self.assertEqual(self.client.get(reverse("connexion_candidat")).status_code, 200)
        self.assertEqual(self.client.get(reverse("espace_candidats")).status_code, 302)
        self.assertEqual(self.client.get(reverse("profil_candidat")).status_code, 302)
        self.assertEqual(self.client.get(reverse("changer_mot_de_passe")).status_code, 302)
        self.assertEqual(self.client.get(reverse("creer_categorie")).status_code, 200)
        self.assertEqual(self.client.get(reverse("creer_mois")).status_code, 200)
        self.assertEqual(self.client.get(reverse("creer_cours")).status_code, 200)

    def test_inscription_candidat(self):
        response = self.client.post(
            reverse("inscription_candidat"),
            {"nom": "dupont", "prenom": "Jean", "mot_de_passe": "testpass123"},
        )
        self.assertRedirects(response, reverse("espace_candidats"))
        self.assertTrue(User.objects.filter(username="dupont", first_name="Jean").exists())

    def test_connexion_candidat(self):
        User.objects.create_user(username="muller", first_name="Anne", password="secret123")
        response = self.client.post(
            reverse("connexion_candidat"),
            {"username": "muller", "password": "secret123"},
        )
        self.assertRedirects(response, reverse("espace_candidats"))

    def test_profil_candidat_apres_connexion(self):
        User.objects.create_user(username="ali", first_name="Ali", password="secret123")
        self.client.login(username="ali", password="secret123")
        response = self.client.get(reverse("profil_candidat"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ali")

    def test_changer_mot_de_passe(self):
        user = User.objects.create_user(username="nina", first_name="Nina", password="ancien123")
        self.client.login(username="nina", password="ancien123")
        response = self.client.post(
            reverse("changer_mot_de_passe"),
            {
                "old_password": "ancien123",
                "new_password1": "nouveauPass456",
                "new_password2": "nouveauPass456",
            },
        )
        self.assertRedirects(response, reverse("profil_candidat"))
        user.refresh_from_db()
        self.assertTrue(user.check_password("nouveauPass456"))

    def test_espace_candidat_demande_abonnement_si_non_abonne(self):
        User.objects.create_user(username="omar", first_name="Omar", password="secret123")
        Cours.objects.create(
            titre="Cours Verrouille",
            description="D",
            categorie=self.categorie_a,
            mois=self.mois_janvier,
            fichier_pdf=self._pdf("locked.pdf"),
        )
        self.client.login(username="omar", password="secret123")
        response = self.client.get(
            reverse("espace_candidats"),
            {"categorie": self.categorie_a.id, "mois": self.mois_janvier.id},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Veuillez vous abonner")
        self.assertNotContains(response, "Cours Verrouille")

    def test_abonnement_donne_acces_aux_cours_du_mois(self):
        user = User.objects.create_user(username="sara", first_name="Sara", password="secret123")
        Cours.objects.create(
            titre="Cours Debloque",
            description="D",
            categorie=self.categorie_a,
            mois=self.mois_janvier,
            fichier_pdf=self._pdf("open.pdf"),
        )
        self.client.login(username="sara", password="secret123")
        response = self.client.post(
            reverse("espace_candidats"),
            {"categorie": self.categorie_a.id, "mois": self.mois_janvier.id},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            Abonnement.objects.filter(
                candidat=user, categorie=self.categorie_a, mois=self.mois_janvier
            ).exists()
        )
        self.assertContains(response, "Cours Debloque")

    def test_creation_categorie(self):
        response = self.client.post(
            reverse("creer_categorie"),
            {"nom": "Marketing", "description": "Description marketing"},
        )
        self.assertRedirects(response, reverse("liste_cours"))
        self.assertTrue(Categorie.objects.filter(nom="Marketing").exists())

    def test_creation_mois(self):
        response = self.client.post(reverse("creer_mois"), {"nom": "Mars", "ordre": 3})
        self.assertRedirects(response, reverse("liste_cours"))
        self.assertTrue(Mois.objects.filter(nom="Mars", ordre=3).exists())

    def test_creation_cours_avec_pdf(self):
        response = self.client.post(
            reverse("creer_cours"),
            {
                "titre": "Python Debutant",
                "description": "Introduction a Python",
                "categorie": self.categorie_a.id,
                "mois": self.mois_janvier.id,
                "fichier_pdf": self._pdf("python.pdf"),
            },
        )
        self.assertRedirects(response, reverse("liste_cours"))
        cours = Cours.objects.get(titre="Python Debutant")
        self.assertEqual(cours.categorie, self.categorie_a)
        self.assertEqual(cours.mois, self.mois_janvier)
        self.assertTrue(cours.fichier_pdf.name.endswith(".pdf"))

    def test_filtre_par_categorie_et_mois(self):
        Cours.objects.create(
            titre="Cours A",
            description="A",
            categorie=self.categorie_a,
            mois=self.mois_janvier,
            fichier_pdf=self._pdf("a.pdf"),
        )
        Cours.objects.create(
            titre="Cours B",
            description="B",
            categorie=self.categorie_b,
            mois=self.mois_fevrier,
            fichier_pdf=self._pdf("b.pdf"),
        )

        response = self.client.get(
            reverse("liste_cours"),
            {"categorie": self.categorie_a.id, "mois": self.mois_janvier.id},
        )
        content = response.content.decode("utf-8")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Cours A", content)
        self.assertNotIn("Cours B", content)

    def test_creation_mois_invalide_refusee(self):
        response = self.client.post(reverse("creer_mois"), {"nom": "Invalide", "ordre": 13})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Le numero du mois doit etre entre 1 et 12.")
        self.assertFalse(Mois.objects.filter(nom="Invalide").exists())

    def test_creation_cours_sans_pdf_refusee(self):
        response = self.client.post(
            reverse("creer_cours"),
            {
                "titre": "Cours Sans Fichier",
                "description": "Description",
                "categorie": self.categorie_a.id,
                "mois": self.mois_janvier.id,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "This field is required.")
        self.assertFalse(Cours.objects.filter(titre="Cours Sans Fichier").exists())

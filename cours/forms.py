from django import forms
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm
from django.contrib.auth.models import User

from .models import Categorie, Cours, Mois


class CategorieForm(forms.ModelForm):
    class Meta:
        model = Categorie
        fields = ["nom", "description"]


class MoisForm(forms.ModelForm):
    class Meta:
        model = Mois
        fields = ["nom", "ordre"]

    def clean_ordre(self):
        ordre = self.cleaned_data["ordre"]
        if ordre < 1 or ordre > 12:
            raise forms.ValidationError("Le numero du mois doit etre entre 1 et 12.")
        return ordre


class CoursForm(forms.ModelForm):
    class Meta:
        model = Cours
        fields = ["titre", "description", "categorie", "mois", "fichier_pdf"]

    def clean_fichier_pdf(self):
        fichier = self.cleaned_data.get("fichier_pdf")
        if not fichier:
            raise forms.ValidationError("Veuillez telecharger un fichier PDF.")

        if not fichier.name.lower().endswith(".pdf"):
            raise forms.ValidationError("Le fichier doit etre au format PDF.")

        return fichier


class InscriptionCandidatForm(forms.Form):
    nom = forms.CharField(max_length=150, label="Nom")
    prenom = forms.CharField(max_length=150, label="Prenom")
    mot_de_passe = forms.CharField(widget=forms.PasswordInput, label="Mot de passe")

    def clean_nom(self):
        nom = self.cleaned_data["nom"].strip()
        if User.objects.filter(username=nom).exists():
            raise forms.ValidationError("Ce nom existe deja. Choisissez un autre nom.")
        return nom

    def save(self):
        nom = self.cleaned_data["nom"].strip()
        prenom = self.cleaned_data["prenom"].strip()
        mot_de_passe = self.cleaned_data["mot_de_passe"]
        return User.objects.create_user(
            username=nom,
            first_name=prenom,
            password=mot_de_passe,
        )


class ConnexionCandidatForm(AuthenticationForm):
    username = forms.CharField(max_length=150, label="Nom")
    password = forms.CharField(widget=forms.PasswordInput, label="Mot de passe")


class ChangerMotDePasseForm(PasswordChangeForm):
    old_password = forms.CharField(widget=forms.PasswordInput, label="Mot de passe actuel")
    new_password1 = forms.CharField(widget=forms.PasswordInput, label="Nouveau mot de passe")
    new_password2 = forms.CharField(
        widget=forms.PasswordInput, label="Confirmer le nouveau mot de passe"
    )

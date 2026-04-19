# 🚀 ΠΛΗΤΡΗ ΟΔΗΓΙΟΣ ΑΝΕΒΑΣΜΑΤΟΣ ΣΤΟ GITHUB

## ✅ ΒΉΜΑ 1: Εγκατάσταση Git

Αν δεν έχεις Git εγκατεστημένο:

### Windows:
1. Κατέβασε από: https://git-scm.com/download/win
2. Εγκατάστησε με τις default ρυθμίσεις
3. Κλείσε και άνοιξε ξανά το PowerShell/CMD

### macOS:
```bash
brew install git
```

### Linux (Ubuntu/Debian):
```bash
sudo apt update && sudo apt install git
```

---

## ✅ ΒΉΜΑ 2: Ρύθμιση Git (πρώτη φορά)

Άνοιξε PowerShell/Terminal και εκτέλεσε:

```bash
git config --global user.name "Το Όνομα Σου"
git config --global user.email "to-email-sou@example.com"
```

---

## ✅ ΒΉΜΑ 3: Αρχικοποίηση Repository

Μέσα στο φάκελο App:

```bash
cd "c:\Users\STAMOS\Desktop\Thesis_Code_Proc_App\Thesis_Code_Proc_App\App"
git init
```

---

## ✅ ΒΉΜΑ 4: Προσθήκη αρχείων

```bash
git add .
```

---

## ✅ ΒΉΜΑ 5: Πρώτο Commit

```bash
git commit -m "Initial commit: ProcureApp - Flask procurement system"
```

---

## ✅ ΒΉΜΑ 6: Δημιουργία Repository στο GitHub

1. Πήγαινε: https://github.com/new
2. Repository name: `ProcureApp` (ή άλλο όνομα)
3. Description: `Flask-based procurement management system`
4. Κάνε το **Public** (άλλα μπορεί και Private)
5. Πάτησε "Create repository"
6. **ΜΗ κάνεις check** τα "Initialize this repository with README" κλπ

---

## ✅ ΒΉΜΑ 7: Σύνδεση με GitHub

Αντικατέστησε `YOUR_USERNAME` και `REPOSITORY_NAME`:

```bash
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/REPOSITORY_NAME.git
git push -u origin main
```

Θα σε ζητήσει username/password (ή Personal Access Token αν έχεις 2FA).

---

## 🔑 ΓΙΑ PERSONAL ACCESS TOKEN (Προτείνεται για ασφάλεια)

1. Πήγαινε: https://github.com/settings/tokens
2. Κάνε κλικ "Generate new token"
3. Δώσε όνομα: "GitHub Desktop" 
4. Επίλεξε scopes: `repo`
5. Κάνε κλικ "Generate token"
6. **Αντιγραφή του token** (δεν θα το ξαναδείς!)
7. Κατά το push, χρήση: 
   - Username: `YOUR_USERNAME`
   - Password: `Το TOKEN που έκοψες`

---

## 🔐 ΓΙΑ SSH (Πιο ασφαλές και ευκολότερο - Προτείνεται)

### 1. Δημιουργία SSH Key

```bash
ssh-keygen -t ed25519 -C "to-email-sou@example.com"
```

Πάτησε Enter για όλες τις προτροπές.

### 2. Προσθήκη key στο ssh-agent

```bash
# Windows:
$env:GIT_SSH_COMMAND="ssh -i $env:USERPROFILE\.ssh\id_ed25519"

# macOS/Linux:
eval "$(ssh-agent -s)"
ssh-add ~/.ssh/id_ed25519
```

### 3. Προσθήκη Public Key στο GitHub

1. Αντιγραφή του key:
```bash
# Windows (PowerShell):
Get-Content $env:USERPROFILE\.ssh\id_ed25519.pub | Set-Clipboard

# macOS/Linux:
cat ~/.ssh/id_ed25519.pub | pbcopy
```

2. Πήγαινε: https://github.com/settings/keys
3. Κάνε κλικ "New SSH key"
4. Επικόλλησε το key και πάτησε "Add SSH key"

### 4. Push με SSH

```bash
git branch -M main
git remote add origin git@github.com:YOUR_USERNAME/REPOSITORY_NAME.git
git push -u origin main
```

---

## 📊 Τι κάνει κάθε εντολή:

| Εντολή | Περιγραφή |
|--------|-----------|
| `git init` | Δημιουργεί νέο git repository |
| `git add .` | Προσθέτει όλα τα αρχεία για commit |
| `git commit -m "..."` | Δημιουργεί checkpoint με περιγραφή |
| `git remote add origin URL` | Συνδέει με GitHub repository |
| `git push -u origin main` | Στέλνει τα commits στο GitHub |

---

## ✏️ Μετά το πρώτο upload - Συνεχόμενες ανανεώσεις:

```bash
# Αλλαγή κάποιων αρχείων...

# Προσθήκη αλλαγών
git add .

# Commit
git commit -m "Περιγραφή αλλαγών"

# Push στο GitHub
git push
```

---

## 🐛 Σύνηθες προβλήματα και λύσεις:

### "fatal: not a git repository"
```bash
cd "c:\Users\STAMOS\Desktop\Thesis_Code_Proc_App\Thesis_Code_Proc_App\App"
git init
```

### "Please tell me who you are" σφάλμα
```bash
git config --global user.name "Your Name"
git config --global user.email "your@email.com"
```

### Λάθος remote URL
```bash
git remote -v  # Δείξε το τρέχον remote
git remote remove origin  # Αφαίρεσε το λάθος
git remote add origin https://github.com/USERNAME/REPO.git  # Πρόσθεσε σωστό
```

### Άρνηση push (Protected Branch)
- Ίσως η `main` branch έχει προστασία
- Δημιουργίησε νέα branch: `git checkout -b develop`
- Push το νέο branch: `git push -u origin develop`

---

## 🎉 Τελική επιβεβαίωση

Μόλις κάνεις push με επιτυχία, θα δεις το repository στο:
```
https://github.com/YOUR_USERNAME/REPOSITORY_NAME
```

Συγχαρητήρια! Το project είναι πλέον online! 🚀

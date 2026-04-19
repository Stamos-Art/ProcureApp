# Ανέβασμα του Project στο GitHub

## 1️⃣ Αρχικοποίηση Git Repository

```bash
cd "c:\Users\STAMOS\Desktop\Thesis_Code_Proc_App\Thesis_Code_Proc_App\App"
git init
```

## 2️⃣ Προσθήκη όλων των αρχείων

```bash
git add .
```

## 3️⃣ Πρώτο Commit

```bash
git commit -m "Initial commit: ProcureApp - Flask-based procurement system"
```

## 4️⃣ Δημιουργία Repository στο GitHub

1. Πήγαινε στο https://github.com/new
2. Δώσε όνομα: `ProcureApp` (ή ό,τι όνομα θέλεις)
3. Προσθετική περιγραφή: `Flask-based procurement management system`
4. Κάνε το **Public** (ή Private αν προτιμάς)
5. Κάνε κλικ "Create repository"

## 5️⃣ Σύνδεση με GitHub

Αντικατέστησε το `USERNAME` και `REPOSITORY_NAME`:

```bash
git branch -M main
git remote add origin https://github.com/USERNAME/REPOSITORY_NAME.git
git push -u origin main
```

## 6️⃣ Ή χρησιμοποίησε SSH (προτείνεται)

Αν έχεις SSH key στο GitHub:

```bash
git remote add origin git@github.com:USERNAME/REPOSITORY_NAME.git
git push -u origin main
```

---

## 📝 Κλειδιά για συνεχόμενες ανανεώσεις:

Μετά τις αλλαγές:

```bash
git add .
git commit -m "Περιγραφή αλλαγών"
git push
```

---

## ⚙️ Προαιρετικά: Setup Python Environment

Για τους που κλωνοποιούν το project:

```bash
# Δημιουργία virtual environment
python -m venv venv

# Ενεργοποίηση (Windows)
venv\Scripts\activate

# Ενεργοποίηση (macOS/Linux)
source venv/bin/activate

# Εγκατάσταση dependencies
pip install -r requirements.txt

# Εκτέλεση
python wsgi.py
```

Το app θα είναι διαθέσιμο στο `http://localhost:5000`

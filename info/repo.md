# Git Repository

GitHub: https://github.com/sjsu-smallwood-group/Temperature-Dependent-PL

## Connect this local clone to the remote

```powershell
git remote add origin https://github.com/sjsu-smallwood-group/Temperature-Dependent-PL.git
git branch -M main
git push -u origin main
```

If a remote named `origin` already exists (e.g. it was added with a wrong URL),
update it instead of adding a new one:

```powershell
git remote set-url origin https://github.com/sjsu-smallwood-group/Temperature-Dependent-PL.git
git push -u origin main
```

# General Github contributing guide

This repo contains code and analysis for the **Ouaga urban heat drivers** project.



## Golden rules

- **Don’t commit directly to `main`.**
- **Always branch from `main`, do your edits, open a Pull Request (PR).**
- **Never merge unreviewed work into `main`.**
- Prefer **“Rebase and merge”** when merging PRs (or **“Squash and merge”** if the branch history is messy).
- Commit **small, logical steps** with clear messages.



## Standard workflow

### 1. Update `main`

Make sure you’re starting from the latest version of `main`.


### 2. Create a branch OR continue working on an existing one

**For new work**: Create a new branch from `main`.
Name it after what you're doing, e.g.:

* `heatwave-analysis`
* `dem-data-pipeline`
* `hotspot-detection`


**To continue existing work**: Switch to your branch and update it with the latest changes from `main`.

```bash
# Switch to your existing branch
git checkout your-branch-name

# Get the latest changes from main
git pull origin main
```
This prevents merge conflicts later and keeps your branch current.

### 3. Do your work and commit

Edit files, run code, etc.

Make small, focused commits. Examples of good commit messages:

* `feat: add hotspot summary table`
* `fix: handle missing ERA5 data`
* `docs: explain GEE authentication`

You can use prefixes to categorise work:

* `feat` for new analysis, pipeline, or main functionality
* `fix` for bug fixes or small corrections to previous work
* `docs` for documentation changes only
* `refactor` for cleaning up code or code restructuring with no functional change
* `test` for adding or updating tests

### 4. Push and open a Pull Request (PR)

Push the branch to `remote` (the shared online version of our project), then on GitHub in a browser:

1. Open a Pull Request.
2. Give it a short title and description (what changed, maybe explanation why).
3. **Request a review** from someone else on the project.

### 5. Merge the PR

After approval:

* Prefer **“Rebase and merge”** (default).
* If the branch has many noisy commits (e.g. “try again”, “fix typo”), use **“Squash and merge”** instead.

Do **not** use “Create a merge commit”.


## If GitHub shows “out of date” or “conflicts”

If GitHub says:

* “This branch is out of date with the base branch”, or
* “Conflicts must be resolved before merging”

and you’re not comfortable with git conflict resolution, just tag someone and comment on the PR:

> “There are conflicts, can someone help resolve?”

For example, Helyne can help update/rebase the branch and push the changes if needed.


## Research-repo tips

These aren’t hard rules, but more like general good practice:

* **Data**

  * Don’t commit large raw datasets. Store them elsewhere (e.g. Zenodo for archived data, Google Drive, or your team's shared storage) and document how to get them.

* **Reproducibility**

  * It's good practice to keep required libraries and environment files up-to-date (`requirements.txt`, `pyproject.toml`, `renv.lock`).
  * Prefer scripts/modules plus a few well-annotated notebooks, not lots of one-off notebooks, unless it's work in progress.
  * Set random seeds in code to ensure consistent results (`np.random.default_rng(42)`)

* **Structure**

  * Keep Python code in `src/`, R code in `R/`, notebooks in `notebooks/`, documentation in `docs/`, tests in `tests/`, and configs in `config/`.


## Core terms (mini dictionary)

* **Repository (repo)**
  The project itself: code, history, issues, PRs.

* **`main`**
  The primary branch that serves as the official, definitive history and the single source of truth for our project. This is like the final edit of a manuscript we want to submit for publication.

* **Branch**
  A separate line of work. You branch off `main` to develop a feature or fix. This is like a draft of a section of our main manuscript - like a draft of the methods section.

* **Commit**
  A collection of file changes with a message. Commits form the history of the project. Think of them like an edited file with a little sticky note on top to your colleagues about what change you made.

* **Pull Request (PR)**
  A request to merge a branch into `main`. Used for review and discussion of work. This is where we discuss the work from your draft and whether it's ready to be put into the main manuscript.

* **Merge**
  Combine changes from one branch into another.

* **Rebase**
  Put the commits from one branch onto the end of another branch, producing a cleaner, linear history. For example, instead of the commit log `A1, B1, B2, A2, B3, A3`, it becomes `A1, A2, A3, B1, B2, B3`

* **Squash**
  Combine multiple commits into one.

* **Remote**
  The copy of the repo on GitHub (usually called `origin`). The local repo is the version of our code on our personal computers, the *remote* is the version of the code on the server that we share.

* **Conflict**
  When there are different changes to the same thing and Git can’t automatically combine changes (e.g. you and someone else edited the same line in a different way). In this situation, Git needs your help to manually confirm which change it should save (your version or theirs).


## Git command cheatsheet

Handy for anyone using the command line.

### Setup (first time)

```bash
# clone the repo
git clone git@github.com:helyne/ouaga-urban-heat-drivers.git
cd ouaga-urban-heat-drivers
```

### Everyday workflow

```bash
# 1. Update main
git checkout main
git pull origin main

# 2. Create a new branch from main
git checkout -b new-work-branch

# Make some changes to files

# 3. See what changed
git status

# 4. Stage and commit changes
git add path/to/file1.py path/to/file2.py
git commit -m "feat: short description of change"

# 5. Push branch to GitHub
git push origin new-work-branch
```

### Keeping your branch up to date (for people comfortable with git)

```bash
# make sure main is current
git checkout main
git pull origin main

# rebase your branch onto main
git checkout new-work-branch
git rebase main

# if conflicts appear:
#   - edit the conflict in the files directly, then save the file
#   - git add <fixed files>
#   - git rebase --continue

# after rebase, update the branch on GitHub
git push --force-with-lease origin new-work-branch
```
# Setting up Nick's Edge Dashboard

Research screen, not a trade signal.

This takes about 30 minutes of clicking, plus building the pages, all free. You only sign in to three places: GitHub, Google and (if you want live crowd data) Myfxbook. Nothing here needs a credit card.

What you need: the file `nicks-edge-dashboard.zip` (unzip it first) and a computer with a web browser.

## Part A. GitHub: the robot that updates the numbers every hour

1. **Sign in to GitHub** (about 5 minutes). Go to github.com and sign in. If you have no account, click "Sign up" and follow the steps. The free plan is enough.

2. **Make a new public repository** (about 2 minutes).
   - Click the "+" at the top right, then "New repository".
   - Name it `nicks-edge-dashboard`.
   - Choose "Public". This keeps the hourly robot free and lets Google Sheets read the numbers. Nothing private is stored in it.
   - Click "Create repository".

3. **Upload the files** (about 3 minutes).
   - On the new repository page, click the link "uploading an existing file".
   - Open the unzipped folder and drag everything inside it into the browser window.
   - Click "Commit changes".

4. **Add the hourly schedule file** (about 3 minutes). Some computers hide this file when you drag folders, so add it by hand.
   - Click "Add file", then "Create new file".
   - In the name box type exactly: `.github/workflows/update.yml`
   - Open `update.yml` from the unzipped folder (the copy is in `.github/workflows/`, or in `workflow_copy/` if you cannot see hidden folders) in a text editor.
   - Copy all of it, paste it into the big box, and click "Commit changes".

5. **Let the robot save its work** (about 1 minute).
   - Click "Settings" (top of the repository), then "Actions", then "General".
   - Scroll to "Workflow permissions", choose "Read and write permissions", and click "Save".

6. **(Optional) Add your Myfxbook login for live crowd numbers** (about 5 minutes).
   - Without this, the crowd part uses the saved snapshot from Oct 23.
   - If you have no Myfxbook account, make a free one at myfxbook.com.
   - In GitHub, click "Settings", then "Secrets and variables", then "Actions", then "New repository secret".
   - Add one secret named `MYFXBOOK_EMAIL` with your Myfxbook email.
   - Add a second secret named `MYFXBOOK_PASSWORD` with your Myfxbook password.
   - Secrets are locked: nobody can read them back, and they never show up in the files.

7. **Run it once now** (about 1 minute, then wait about 5 minutes).
   - Click "Actions" at the top. If asked, click "I understand my workflows, go ahead and enable them".
   - Click "Update Nick's Edge Dashboard" on the left, then "Run workflow", then the green "Run workflow" button.
   - When the dot turns into a green tick, the `output` folder is full of fresh numbers.
   - From now on it runs every hour by itself, plus once more on Friday afternoon after the weekly COT report.

## Part B. Google Sheets: where the numbers land

8. **Sign in to Google and make the Sheet** (about 3 minutes).
   - Go to sheets.new and sign in with your Google account. A blank sheet opens.
   - Click "File", then "Import", then "Upload", and pick `starter/Nicks_Edge_Dashboard_starter.xlsx`.
   - Choose "Replace spreadsheet" and click "Import data".
   - Rename the sheet "Nick's Edge Dashboard" (click the title at the top left).

9. **Point it at your GitHub** (about 1 minute).
   - On the Setup tab, type your GitHub username in the yellow cell B2.
   - Wait a minute. Each tab, such as top_setups and news_risk, fills with numbers.
   - If a tab shows the formula as plain text instead of numbers, do step 10 and use menu item "1. Set up data tabs".

10. **(Optional) Add the helper menu** (about 4 minutes).
    - Click "Extensions", then "Apps Script".
    - Delete what is in the box, paste everything from `apps_script/LookerLink.gs`, and click the disk icon to save.
    - Close that tab and reload the Sheet. A new menu "Nick's Edge" appears.
    - The first time you use it, Google asks you to allow it: click "Continue", pick your account, then "Allow". It only reads your own Sheet and your public GitHub files.
    - The menu has "Refresh data now" and "Make Looker Studio link".

## Part C. Looker Studio: the dashboard pages

11. **Open Looker Studio with your data** (about 3 minutes).
    - Use the menu "Nick's Edge", then "3. Make Looker Studio link", and click the link.
    - If you skipped step 10, instead go to lookerstudio.google.com, click "Blank report", choose "Google Sheets", pick your sheet and the top_setups tab.
    - Click "Edit and share", then "Acknowledge and save".

12. **Build the 19 pages** (about 2 to 3 hours by hand, or let the assistant do it).
    - Follow `LOOKER_SPEC.md` page by page.
    - The easy way: once you are signed in to Google, tell the assistant "build the Looker pages" and it will do this part for you on its own browser while you watch.

13. **Keep it private** (about 1 minute).
    - In Looker Studio, click "Share". Leave it shared only with yourself unless you want to show someone.

## Turning parts on or off

- Open `config.json` in GitHub and click the pencil icon.
- Change `true` to `false` for any part: for example `"news_risk": false` turns off the news warning, and `"news_risk_medium_impact": false` hides the lighter medium tags.
- Click "Commit changes". The next hourly run uses the new setting.

## If something looks wrong

- The `updates_log` tab (page 19) shows each data source and whether it was OK, CACHED (old but usable), SNAPSHOT or MISSING.
- In GitHub, "Actions" shows each hourly run. A red cross means a run failed. The dashboard then keeps the last good numbers.

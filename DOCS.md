# KmartBot Beginner Guide

This guide explains how to start the app, set it up, and run your first tasks.

## What This App Does

KmartBot is a local checkout bot for `kmart.com.au`.

You manage everything from the web dashboard:

- `Tasks`: create and run checkout tasks
- `Profiles`: save shipping/billing details
- `Cards`: save payment cards
- `Settings`: save webhooks and email-generation settings

The app runs only on your machine unless you choose to send Discord webhook notifications.

## Before You Start

You should already have:

- macOS
- Python virtual environment created in `.venv`
- Node/npm installed for the dashboard

Project root:

```bash
/Users/bayli/Desktop/kmartbot
```

## Starting The App

Open Terminal:

```bash
cd /Users/bayli/Desktop/kmartbot
source .venv/bin/activate
```

### Development mode

Use this if you want the React dashboard with hot reload.

Backend:

```bash
python3 run.py --reload
```

Dashboard:

```bash
cd /Users/bayli/Desktop/kmartbot/dashboard
npm run dev
```

Open:

- Dashboard: [http://localhost:5173](http://localhost:5173)
- Backend API: [http://localhost:8080](http://localhost:8080)

### Production-style mode

Use this if you want one command and one port:

```bash
cd /Users/bayli/Desktop/kmartbot
source .venv/bin/activate
python3 run.py --build-ui
```

Open:

- App: [http://localhost:8080](http://localhost:8080)

## First-Time Setup

Recommended order:

1. Add a profile
2. Add a card
3. Configure settings
4. Create a task
5. Start the task

## Profiles Page

Profiles are your shipping and billing details.

Typical fields:

- Profile name: a label like `Home`, `Main`, or `Reshipper 1`
- First name / last name
- Email
- Mobile
- Address
- State and postcode
- Flybuys number if you use one

You need at least one profile before creating a task.

### CSV import/export

Use the `Import CSV` and `Export CSV` buttons at the top of the page.

Profile CSV columns:

```text
name,first_name,last_name,email,mobile,address1,address2,city,state,postcode,country,flybuys
```

## Cards Page

Cards are stored locally in the SQLite database on your machine.

Typical fields:

- Alias: label like `ANZ Visa` or `Main Card`
- Cardholder name
- Card number
- Expiry month
- Expiry year
- CVV

You need at least one card before a task can run.

### CSV import/export

Use the `Import CSV` and `Export CSV` buttons at the top of the page.

Card CSV columns:

```text
alias,cardholder,number,expiry_month,expiry_year,cvv
```

## Settings Page

This page stores global settings for the whole app.

Important settings:

- `Success / failure webhook`: Discord webhook for task results
- `3DS challenge webhook`: separate Discord webhook for 3DS challenge alerts
- `Catch-all domain`: for generated order emails
- `Gmail base address`: for Gmail `+alias` email generation
- `Gmail sub-address spoofing`: enable Gmail alias generation
- `Staff discount codes`: global toggle for staff code usage

Click `Save` in the header after making changes.

## Tasks Page

Tasks are the actual checkout jobs.

Each task needs:

- SKU
- Profile
- At least one card
- Quantity

Optional task settings:

- Name
- Staff discount toggle
- Flybuys toggle
- Watch mode

### Watch mode

Watch mode is for waiting on stock.

When enabled, the task:

- solves Akamai
- creates a cart
- adds the SKU to cart
- keeps checking shipping availability
- moves into checkout automatically when stock becomes shippable

This is useful for limited releases where home delivery flips live later.

### Standard run

If watch mode is off, the task tries to cart and check out immediately.

### Logs

Expand a task row to see logs.

Each new run starts with a fresh log stream. Old logs from previous runs are cleared for that task when it starts again.

### Start and stop

Available controls:

- `Start`: starts one task
- `Stop`: stops one task
- `Start all`: starts all eligible tasks
- `Stop all`: stops all running tasks

Stopping is safe. The bot handles cancellation cleanly.

### CSV import/export

Use the `Import CSV` and `Export CSV` buttons in the Tasks header.

Task CSV columns:

```text
name,site,sku,profile_id,profile_name,card_ids,card_aliases,quantity,use_staff_codes,use_flybuys,watch_mode
```

Notes:

- `site` should normally be `kmart`
- `profile_id` or `profile_name` must be present
- `card_ids` or `card_aliases` can be used
- multiple cards should be separated with `|`
- booleans can be values like `true`, `false`, `1`, `0`, `yes`, `no`

Portable example using names instead of IDs:

```csv
name,site,sku,profile_name,card_aliases,quantity,use_staff_codes,use_flybuys,watch_mode
PS5 Drop,kmart,43675449,Home,Main Card|Backup Card,1,true,true,true
```

Important:

- task import will fail if the referenced profile or card does not exist
- task import will also fail if a profile name or card alias matches more than one record

Best workflow:

1. Import profiles
2. Import cards
3. Import tasks

## Data Files

Useful local files:

- `data/kmartbot.db`: app database
- `data/proxies.txt`: proxy list
- `data/staff_codes.txt`: staff discount codes
- `config.json`: local config file

These files are local-only and should not be committed with secrets.

## Proxies

If you want proxies, put them in:

```text
data/proxies.txt
```

Supported formats:

- `host:port`
- `host:port:user:pass`
- `user:pass@host:port`

If the file is empty, the app runs without proxies.

## Staff Codes

If you use staff discount codes, put one code per line in:

```text
data/staff_codes.txt
```

Blank lines and lines starting with `#` are ignored.

The app rotates through the codes automatically.

## Typical Beginner Workflow

### Fast manual setup

1. Start the app
2. Go to `Profiles` and add one profile
3. Go to `Cards` and add one card
4. Go to `Settings` and save your webhook or email settings
5. Go to `Tasks`
6. Create a new task with SKU, profile, and card
7. Click `Start`
8. Expand logs to watch progress

### Bulk setup with CSV

1. Start the app
2. Go to `Profiles` and import your profile CSV
3. Go to `Cards` and import your card CSV
4. Go to `Tasks` and import your task CSV
5. Start one task first to verify your data
6. Then use `Start all` if needed

## What The Statuses Mean

- `idle`: task has not started yet
- `running`: task is currently active
- `success`: task checked out successfully
- `failed`: task hit an error
- `stopped`: task was manually stopped

## Common Problems

### Task says no cards assigned

The task does not have any card attached. Edit the task and select at least one card.

### Task says profile not found

The selected profile was deleted or the imported task references the wrong profile.

### CSV import fails

Usually one of these:

- required column is missing
- a required value is blank
- boolean value is invalid
- task references a profile/card that does not exist
- task references a duplicate profile name or duplicate card alias

If this happens, fix the CSV row mentioned in the error and re-import.

### No dashboard opens in dev mode

Make sure both processes are running:

- `python3 run.py --reload`
- `cd dashboard && npm run dev`

### Built mode shows an old UI

Rebuild the dashboard:

```bash
cd /Users/bayli/Desktop/kmartbot
source .venv/bin/activate
python3 run.py --build-ui
```

## Safety Notes

- This app stores card data locally in plain text inside the SQLite database
- Do not expose the backend to the internet
- Do not commit `config.json`, proxies, staff codes, or the live database

## Recommended Habit

Before a real drop:

1. Test with one task
2. Confirm profile and card data are correct
3. Confirm webhooks work
4. Confirm the SKU is correct
5. Only then run multiple tasks


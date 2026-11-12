# Saved copy of the solarbot dashboard on the second Pi

What this does: the second Pi (always on) downloads what the public dashboard shows every 2 minutes and keeps it as plain files. When the solar Pi is off, visitors get these files instead. The solar Pi holds no keys or passwords and nothing is uploaded from it. The second Pi only does read only GET requests to the public page, the same as any visitor.

## What you need on the second Pi

- python3 (nothing to install, the script uses only the standard library)
- one file: `export-snapshot.py`
- a web server that can serve a folder (nginx, Apache, caddy, or even `python3 -m http.server`)

## Set up

1.  Make a folder for the copy, for example `/var/www/solarbot-copy`
2.  Copy `export-snapshot.py` to the second Pi, for example to `/home/pi/solarbot-mirror/`
3.  Run it once by hand and look at the output:

        python3 /home/pi/solarbot-mirror/export-snapshot.py --from-url https://solarbot.cmama.xyz /var/www/solarbot-copy

    Expected: `mirror: ... written, 92 files updated, N days, data up to <date>`.
    If the solar Pi is off at that moment it says `source is offline or shows a saved copy itself; the old copy is left as it is`. That is correct, it never overwrites a good copy with an offline page.

4.  Run it every 2 minutes. With cron (`crontab -e`):

    */2 * * * * python3 /home/pi/solarbot-mirror/export-snapshot.py --from-url https://solarbot.cmama.xyz /var/www/solarbot-copy >> /home/pi/solarbot-mirror/mirror.log 2>&1

5.  Serve the folder with the web server and give it an address, for example solarbot-copy.cmama.xyz through the tunnel you already have.

## Good to know

- Days that are over are downloaded once. Each run only fetches the newest 2 days and the question list, so it is light for the solar Pi.
- Exit code 3 means "source offline, nothing changed". Any other failure also leaves the old copy as it is.
- The page of the copy has no controls and nothing writes to anything.
- To remove it: delete the cron line and the folder.

## Still to decide

- The Worker on solarbot.cmama.xyz must send visitors to the copy when the solar Pi is off (a small change in cloudflare-worker/src/index.js, only after the copy runs).

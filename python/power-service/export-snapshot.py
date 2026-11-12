#!/usr/bin/env python3
"""Freeze the power page and its history into plain files, so it can stay online while the Pi is off.

The live page is a Python server (pmic-web.py): every number comes from an /api/... call, so with the Pi off there is
nothing to answer. This script starts that same server on a spare port against a COPY of the data folder, asks it for
everything the page asks for, and saves the answers as files. The page is then patched so its fetch() calls read those
files instead, the tabs that need the live Pi are hidden, and a line at the top says how old the data is.

    python3 export-snapshot.py [DATA_DIR] [OUT_DIR] [--port 8431]

DATA_DIR defaults to ~/solarbot/data/power (what the service writes), OUT_DIR to ./snapshot. Put OUT_DIR on any static
host. Run it on the Pi when you can: ecocost (the cloud comparison) is installed there, and the panel needs it.
Nothing in DATA_DIR is changed, and nothing is uploaded from here.

MIRROR MODE (for a second, always-on machine that has no copy of the data):

    python3 export-snapshot.py --from-url https://solarbot.cmama.xyz OUT_DIR

Instead of starting the page server it downloads what the PUBLIC page shows (read-only GET requests, nothing to log in to,
no key or token) and writes the same saved copy into OUT_DIR. Run it every 2 minutes (cron or a systemd timer).
Safe by design: if the source does not answer, answers with its own offline/saved page, or anything it needs fails, the
script stops and the copy that is already in OUT_DIR is left exactly as it was. Days that are over are fetched once;
only the newest 2 days and the question list are fetched again each run.
"""
import json, os, re, shutil, subprocess, sys, tempfile, time, urllib.error, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
DAY_FILE = re.compile(r"power-(\d{4}-\d{2}-\d{2})\.csv$")


def key(url):
    # api/history?day=2026-09-18 -> api_history_day_2026_09_18  (the page-side shim builds the same name)
    return re.sub(r"[^A-Za-z0-9]+", "_", url).strip("_")


def main():
    args = sys.argv[1:]
    if "--from-url" in args:
        i = args.index("--from-url")
        url = args[i + 1]
        del args[i:i + 2]
        mirror(url, os.path.abspath(args[0] if args else "snapshot"))
        return
    port = 8431
    if "--port" in args:
        i = args.index("--port")
        port = int(args[i + 1])
        del args[i:i + 2]
    data_dir = os.path.expanduser(args[0] if args else "~/solarbot/data/power")
    out = os.path.abspath(args[1] if len(args) > 1 else "snapshot")
    if not os.path.isdir(data_dir):
        sys.exit("no data folder: " + data_dir)

    # the server writes into its data folder while it runs (the sampler), so it gets a copy
    work = tempfile.mkdtemp(prefix="snapshot-data-")
    days = []
    for n in sorted(os.listdir(data_dir)):
        m = DAY_FILE.fullmatch(n)
        if m or n in ("questions.jsonl", "imported-esp32.jsonl"):
            shutil.copy2(os.path.join(data_dir, n), os.path.join(work, n))
            if m:
                days.append(m.group(1))
    days.sort(reverse=True)

    env = dict(os.environ, POWER_DATA_DIR=work, PMIC_WEB_PORT=str(port))
    srv = subprocess.Popen([sys.executable, os.path.join(HERE, "pmic-web.py")], env=env,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = "http://127.0.0.1:%d/" % port

    def get(path, binary=False):
        with urllib.request.urlopen(base + path, timeout=60) as r:
            b = r.read()
        return b if binary else b.decode("utf-8", "replace")

    try:
        for _ in range(40):
            try:
                get("api/days")
                break
            except Exception:
                time.sleep(0.5)
        else:
            sys.exit("the page server did not start")

        # empty the folder but keep the folder itself (a web server may be sitting in it)
        if os.path.isdir(out):
            for n in os.listdir(out):
                p = os.path.join(out, n)
                shutil.rmtree(p) if os.path.isdir(p) else os.remove(p)
        os.makedirs(os.path.join(out, "data"), exist_ok=True)

        def save(rel, content):
            p = os.path.join(out, rel)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "wb") as f:
                f.write(content if isinstance(content, bytes) else content.encode("utf-8"))

        def api(url, name=None):
            try:
                body = get(url)
            except urllib.error.URLError as e:
                body = json.dumps({"error": str(e)})
            save("data/%s.json" % (name or key(url)), body)
            return body

        # what the page asks for, one file each. The day list comes from the source folder, not from the copy.
        save("data/%s.json" % key("api/days"), json.dumps({"days": days}))
        for d in days:
            api("api/history?day=" + d)
        api("api/questions")
        api("api/imported")
        api("api/files")
        api("api/models")
        api("api/samples")
        cmp_default = json.loads(api("api/compare"))
        for mname in (cmp_default.get("models") or []):
            api("api/compare?model=" + mname)

        # downloads the page links to
        save("download/questions.csv", get("download/questions.csv", True))
        for n in ("questions.jsonl",) + tuple("power-%s.csv" % d for d in days):
            try:
                save("download/" + n, get("download/" + n, True))
            except Exception:
                pass
        save("download/report.html", get("download/report.html", True))

        # the bot's face is hidden in the snapshot, but the page preloads the frames
        faces = os.path.join(HERE, "faces")
        if os.path.isdir(faces):
            for st in os.listdir(faces):
                for i in "012":
                    try:
                        save("faces/%s/%s.png" % (st, i), get("faces/%s/%s.png" % (st, i), True))
                    except Exception:
                        pass

        # when the newest data point is from
        newest = 0
        for d in days[:1]:
            try:
                h = json.loads(open(os.path.join(out, "data", key("api/history?day=" + d) + ".json"), encoding="utf-8").read())
                newest = max(newest, int(max((r[0] for r in h.get("points", [])), default=0)))
            except Exception:
                pass
        q_last = 0
        try:
            for line in open(os.path.join(work, "questions.jsonl"), encoding="utf-8"):
                try:
                    q_last = max(q_last, int(json.loads(line).get("t", 0)))
                except Exception:
                    pass
        except OSError:
            pass
        last = max(newest, q_last) or (int(os.path.getmtime(os.path.join(work, "power-%s.csv" % days[0]))) if days else 0)
        meta = {"saved": int(time.time()), "last_data": last, "days": len(days)}
        save("data/snapshot.json", json.dumps(meta))
        save("data/%s.json" % key("api/snapshot"), json.dumps(meta))   # what the page asks for

        page = patch_page(get(""))
        save("index.html", page)
        print("snapshot written to %s: %d days, data up to %s" % (
            out, len(days), time.strftime("%Y-%m-%d %H:%M", time.localtime(last)) if last else "n/a"))
    finally:
        srv.terminate()
        try:
            srv.wait(10)
        except Exception:
            srv.kill()
        shutil.rmtree(work, ignore_errors=True)


def mirror(url, out):
    """Build the saved copy from the public page at url. Writes nothing unless everything was fetched."""
    base = url.rstrip("/") + "/"

    def fetch(path, binary=False):
        req = urllib.request.Request(base + path, headers={"User-Agent": "solarbot-mirror/1"})
        with urllib.request.urlopen(req, timeout=60) as r:
            b = r.read()
            hdr = {k.lower(): v for k, v in r.headers.items()}
        return b, hdr

    def stop(msg):
        print("mirror: " + msg + "; the old copy is left as it is")
        sys.exit(3)

    try:
        home, hdr = fetch("")
    except Exception as e:
        stop("source not reachable (%s)" % e)
    if hdr.get("x-solarbot-status") == "snapshot" or b"(saved copy)" in home or b"Solarbot power" not in home:
        stop("source is offline or shows a saved copy itself")

    new = {}                                   # relative path -> bytes, written only when all of it worked

    def api(u, name=None, reuse=False):
        rel = "data/%s.json" % (name or key(u))
        old = os.path.join(out, rel)
        if reuse and os.path.isfile(old):
            return open(old, "rb").read().decode("utf-8", "replace")
        try:
            b, _ = fetch(u)
            json.loads(b.decode("utf-8"))      # must be real JSON, not an error page
        except Exception as e:
            stop("could not fetch %s (%s)" % (u, e))
        new[rel] = b
        return b.decode("utf-8")

    days = sorted(json.loads(api("api/days")).get("days", []), reverse=True)
    if not days:
        stop("source has no days")
    for i, d in enumerate(days):
        api("api/history?day=" + d, reuse=i >= 2)      # a finished day never changes
    q_old = ""
    try:
        q_old = open(os.path.join(out, "data", key("api/questions") + ".json"), encoding="utf-8").read()
    except OSError:
        pass
    q_new = api("api/questions")
    same_q = (q_old == q_new)
    for u in ("api/imported", "api/files", "api/models", "api/samples"):
        api(u)
    cmp_default = json.loads(api("api/compare"))
    for m in (cmp_default.get("models") or []):
        api("api/compare?model=" + m, reuse=same_q)      # only changes when the questions change

    def dl(name):
        rel = "download/" + name
        if not same_q or not os.path.isfile(os.path.join(out, rel)) or name.startswith("power-" + days[0]) or (len(days) > 1 and name.startswith("power-" + days[1])):
            try:
                new[rel] = fetch("download/" + name)[0]
            except Exception:
                pass
    dl("questions.csv"); dl("questions.jsonl"); dl("report.html")
    for d in days:
        dl("power-%s.csv" % d)

    states = re.findall(r"'([a-z]+)'", (re.search(r"FACES\s*=\s*\[([^\]]*)\]", home.decode("utf-8", "replace")) or [None, ""])[1])         or ["idle", "listening", "recognizing", "answering", "detecting"]
    for st in states:
        for i in "012":
            rel = "faces/%s/%s.png" % (st, i)
            if not os.path.isfile(os.path.join(out, rel)):
                try:
                    new[rel] = fetch(rel)[0]
                except Exception:
                    pass

    newest = 0
    try:
        h = json.loads(api("api/history?day=" + days[0], reuse=True))
        newest = int(max((r[0] for r in h.get("points", [])), default=0))
    except Exception:
        pass
    q_last = 0
    try:
        for q in json.loads(q_new).get("questions", []):
            q_last = max(q_last, int(q.get("t", 0)))
    except Exception:
        pass
    meta = json.dumps({"saved": int(time.time()), "last_data": max(newest, q_last), "days": len(days)}).encode()
    new["data/snapshot.json"] = meta
    new["data/%s.json" % key("api/snapshot")] = meta
    new["index.html"] = patch_page(home.decode("utf-8", "replace")).encode("utf-8")

    for rel, content in new.items():           # everything is in hand: now write, each file replaced in one step
        p = os.path.join(out, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p + ".tmp", "wb") as f:
            f.write(content)
        os.replace(p + ".tmp", p)
    print("mirror: %s written, %d files updated, %d days, data up to %s" % (
        out, len(new), len(days), time.strftime("%Y-%m-%d %H:%M", time.localtime(max(newest, q_last))) if max(newest, q_last) else "n/a"))


def patch_page(s):
    def swap(old, new):
        nonlocal s
        if s.count(old) != 1:
            sys.exit("the page changed: expected exactly one match for: " + old[:70])
        s = s.replace(old, new)

    # 1. the page keeps its look. What needs the live Pi (the numbers under the title, the Live and Calibration tabs)
    #    gets a dark grey box with a message on top of it; nothing is greyed out, and the Live tab stays the home page
    swap(" .phasebar{margin-top:12px}\n",
         " /* snapshot: a message box over what needs the live Pi */\n"
         " .veilbox{position:relative}\n"
         " .veil{position:absolute;top:0;left:0;right:0;bottom:0;z-index:5;pointer-events:none;display:flex;\n"
         "   align-items:flex-start;justify-content:center;padding:60px 16px 16px;box-sizing:border-box}\n"
         " .veil.small{align-items:center;padding:6px}\n"
         " .veil div{max-width:440px;background:rgba(74,74,74,.8);color:#fff;padding:12px 16px;font-size:15px;line-height:1.45;text-align:center}\n"
         " .veil b{display:block;font-size:17px;margin-bottom:4px}\n"
         " .veil i{display:block;font-style:normal;opacity:.8;font-size:13px;margin-top:6px}\n"
         " .veil.graph{display:block}\n"
         " .veil.graph div{position:absolute;left:50%;transform:translate(-50%,-50%);width:min(560px,86%);box-sizing:border-box;\n"
         "   padding:24px 30px;font-size:19px}\n"
         " .veil.graph b{font-size:28px;margin-bottom:8px}\n"
         " .veil.graph i{font-size:14px;margin-top:10px}\n"
         " .phasebar{margin-top:12px}\n")
    # 3. nothing to poll; the first calls at start-up are enough
    swap("setInterval(poll,1000);setInterval(qlog,2000);setInterval(files,30000);",
         "/* snapshot: the data does not change, so nothing is polled */")
    # 4. fetch() reads the saved files; anything that would change something is refused
    shim = ("<script>\n(function(){var real=window.fetch;\n"
            "window.fetch=function(u,o){\n"
            "  if((o&&o.method&&o.method!=='GET')||typeof u!=='string'||u.indexOf('api/')!==0) return Promise.reject(new Error('snapshot'));\n"
            "  return real('data/'+u.replace(/[^A-Za-z0-9]+/g,'_').replace(/^_+|_+$/g,'')+'.json');};})();\n</script>\n")
    note = ('<script>addEventListener("DOMContentLoaded",function(){'
            'fetch("api/snapshot").then(function(r){return r.json();}).catch(function(){return {};}).then(function(m){'
            'var t=m.last_data?new Date(m.last_data*1000).toLocaleString([], {dateStyle:"medium",timeStyle:"short"}):"";'
            'var full="<div><b>The Pi is currently offline</b>so there is no live data feed. See the History, Static and Report tabs for the saved data."'
            '+(t?"<i>Saved data goes up to "+t+"</i>":"")+"</div>";'
            'var small="<div>no live feed</div>";'
            '[["#tab-live",full],["#tab-calib",full]].forEach(function(v){'
            'var el=document.querySelector(v[0]);if(!el)return;el.classList.add("veilbox");'
            'var d=document.createElement("div");d.className="veil"+(v[2]?" small":"");d.innerHTML=v[1];el.appendChild(d);});'
            # on the Live tab the message sits in the middle of the graph, and follows it when the window changes or the tab opens
            'var live=document.getElementById("tab-live"),cv=document.getElementById("c");'
            'var lv=live&&live.querySelector(".veil");'
            'if(lv&&cv){lv.classList.add("graph");var place=function(){var a=cv.getBoundingClientRect(),b=live.getBoundingClientRect();'
            'if(!a.height)return;var bx=lv.firstChild;bx.style.top=(a.top-b.top+a.height/2)+"px";};'
            'place();addEventListener("resize",place);setTimeout(place,300);'
            'document.querySelectorAll(".tabs button").forEach(function(x){x.addEventListener("click",function(){setTimeout(place,50);});});}'
            'var g=document.getElementById("doing");if(g)setTimeout(function(){g.textContent="offline";},1200);});});'
            '</script>\n')
    # the page has no <body> tag of its own: the shim and the message script go before the header
    swap("</style>\n<header>\n", "</style>\n" + shim + note + "<header>\n")
    swap("<title>Solarbot power</title>", "<title>Solarbot power (saved copy)</title>")
    return s


if __name__ == "__main__":
    main()

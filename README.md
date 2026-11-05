# WhatsApp Cloud Console — Render par deploy

Yeh project aapke diye `app.py` dashboard ke embedded HTML/CSS/JavaScript ko rakhta hai; alag frontend build nahi hai. Dashboard par visible login page nahi hai. UI actions ke liye browser pehli baar `ADMIN_API_KEY` maangega; API key server ke Render environment mein hi configure hoti hai, code/HTML mein hard-code nahi hoti. Visual layout/CSS wahi rakha hai; sirf Cloud API ke liye zaroori copy/behavior, group option disable, aur send se pehle consent/policy confirmation add kiya hai.

## Is build ki seemaen

- Official WhatsApp Business Cloud API hi use hoti hai; personal WhatsApp QR/device-pairing nahi.
- Is console mein sirf individual numbers ko plain-text messages bhejne ka flow hai. Group list/group sending aur approved-template sending enabled nahi hain.
- App ke current plain-text message ke liye har recipient ka explicit opt-in aur open 24-hour customer-service window zaroori hai. Window ke bahar approved template chahiye. Browser confirmation aapki attestation hai, consent ka independent record nahi—apne opt-in records alag se rakhein.
- Meta ka “accepted” response delivery ka proof nahi hota. Delivery/read/failure statuses webhook se aate hain.
- Bulk tasks is lightweight build mein web process ke background thread mein chalte hain. Service restart ke beech task ruk sakta hai; ambiguous timeout par app automatic resend nahi karti. Render Free web service 15 minute bina traffic ke baad sleep ho sakti hai; free service ka local SQLite data restart/redeploy/sleep par mit sakta hai, aur Free Postgres 30 din baad expire hota hai. Uptime ki guarantee nahi hoti. Continuous/production use ke liye current paid persistent database aur reliable worker setup karein.
- WhatsApp live credentials abhi source mein nahi hain. Unhe aapko apne Meta account se lekar Render ke Environment mein set karna hoga; tab tak dashboard disconnected rahega aur sending blocked hogi.

## Render par deploy — sabse aasaan tareeqa

1. ZIP extract karein. GitHub par **New repository** banayein (Private recommended), phir **Add file → Upload files** se extracted folder ke andar ke files repository ke root mein upload karke **Commit changes** karein. `render.yaml` root mein hona chahiye. `.env.example` sample hai; real `.env` ya API token GitHub par upload na karein.
2. Meta Developer account mein Business app banayein, WhatsApp product add karein, aur apne business phone number ko Cloud API ke saath set up karein. Meta se access token, Phone Number ID, Business Account ID aur App Secret lein. Production messaging se pehle business verification/number setup jo Meta maange, complete karein. Is project mein user ke credentials nahi diye gaye hain.
3. Render Dashboard mein **New → Blueprint** choose karke GitHub repository connect karein aur `render.yaml` apply karein. Blueprint se web service banegi. Secret prompts mein:
   - `ADMIN_API_KEY`: apna lamba random secret banayein, jaise apne computer par `python -c "import secrets; print(secrets.token_urlsafe(32))"` chalakar. Is value ko sirf Render Environment mein save karein. Browser mein dashboard ke kisi action par wahi key enter karein.
   - `WHATSAPP_ACCESS_TOKEN`: Meta WhatsApp Cloud API access token.
   - `WHATSAPP_PHONE_NUMBER_ID`: Meta dashboard ka **Phone Number ID** (phone number nahi).
   - `WHATSAPP_BUSINESS_ACCOUNT_ID`: optional reference; is starter mein direct message request ke liye zaroori nahi.
   - `WHATSAPP_VERIFY_TOKEN`: apna random webhook verification text.
   - `WHATSAPP_APP_SECRET`: Meta app ka App Secret (webhook signature verify karne ke liye).
   `FLASK_SECRET_KEY` Blueprint se auto-generate hoti hai. WhatsApp token/App Secret ko frontend, chat, ya public repository mein kabhi na daalein; fake/dummy credentials na bharein.
4. Blueprint mein build command `pip install -r requirements.txt`, start command `gunicorn --workers 1 --threads 4 --timeout 120 --access-logfile - --error-logfile - app:app`, aur health path `/health` pehle se configured hain. Deploy successful hone par Render URL kholein; dashboard seedha khulega, login page nahi.
5. UI ke **WhatsApp Cloud API Connection** panel mein apna Meta business phone E.164 format mein `+` aur country code ke saath daalein; Verify par click karein. Key prompt aaye to Render wala `ADMIN_API_KEY` enter karein. “Connected” tabhi aayega jab Meta Graph API credentials ko verify kare.
6. Webhook ke liye Meta Developer Dashboard mein callback URL `https://YOUR-RENDER-URL/webhook/whatsapp` daalein. `WHATSAPP_VERIFY_TOKEN` bilkul same hona chahiye, aur `messages` webhook field subscribe karein. Webhook signatures `WHATSAPP_APP_SECRET` se verify hoti hain.
7. Ek opted-in test number ke liye number field use karein; multiple recipients ke liye `.txt` file mein **har line par ek E.164 number** likhein, jaise `+919876543210`. Pehle sirf ek opted-in test number use karein. App `DEFAULT_MESSAGE` environment variable ka text (default `Hello from Virat Rajput`) aur optional prefix bhejti hai. Dashboard par confirmation dialog mein tabhi Yes karein jab explicit opt-in aur 24-hour window dono sahi hon.

## Database aur data persistence

Bina `DATABASE_URL` ke app SQLite use karti hai; Render par local files ephemeral ho sakti hain. Task history deploy/restart par kho sakti hai. Persistent task history ke liye Render par PostgreSQL database banayein, phir uska **Internal Database URL** web service ke `DATABASE_URL` environment variable mein set karein. App Render ke `postgres://`/`postgresql://` URL ko psycopg driver ke saath use karegi. Database create karte waqt Render dashboard mein current plan/cost dekh lein; Blueprint isliye automatic paid database nahi banata.

## Local test

```bash
python -m venv .venv
source .venv/bin/activate        # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env             # Windows par manually copy karein
# .env mein ADMIN_API_KEY set karein; WhatsApp values ke bina actual send enable nahi hoga
python app.py
```

Open `http://127.0.0.1:5000`. Tests (Meta ko koi live request nahi bhejte):

```bash
pytest -q
```

## Official references

- [Render Flask deploy guide](https://render.com/docs/deploy-flask)
- [Meta WhatsApp Cloud API: send messages, opt-in and 24-hour window](https://developers.facebook.com/documentation/business-messaging/whatsapp/messages/send-messages)
- [Meta WhatsApp Cloud API getting started](https://developers.facebook.com/documentation/business-messaging/whatsapp/get-started)
- [Meta webhook endpoint setup](https://developers.facebook.com/documentation/business-messaging/whatsapp/webhooks/create-webhook-endpoint/)

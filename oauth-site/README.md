# NewsFlow — сайт для Google OAuth

Эта папка готова для **Cloudflare Pages Direct Upload**. Загружайте именно её
содержимое, чтобы `index.html` лежал в корне проекта Pages.

## Публикация через Cloudflare Pages

1. Войдите в [Cloudflare Dashboard](https://dash.cloudflare.com/).
2. Откройте **Workers & Pages** → **Create application** → **Pages** →
   **Upload assets** / **Direct Upload**.
3. Назовите проект, например `newsflow-site`, и загрузите содержимое этой
   папки: `index.html`, `404.html`, `assets/`, `privacy/`, `terms/`.
4. После первого deployment откройте **Custom domains** и добавьте
   `tinkbro.ru`. При необходимости добавьте также `www.tinkbro.ru`.
5. Cloudflare покажет точные DNS-записи или предложит перенести управление
   DNS-зоной. Вносите только те значения, которые покажет Cloudflare для
   созданного Pages-проекта.
6. Дождитесь, пока откроются эти адреса по HTTPS:
   - `https://tinkbro.ru/`
   - `https://tinkbro.ru/privacy/`
   - `https://tinkbro.ru/terms/`

## Google OAuth

1. В Google Search Console подтвердите владение доменом `tinkbro.ru` тем же
   Google-аккаунтом, у которого есть доступ к проекту Google Cloud.
2. В **Google Auth Platform → Branding** внесите:
   - Application home page: `https://tinkbro.ru/`
   - Application privacy policy link: `https://tinkbro.ru/privacy/`
   - Application terms of service link: `https://tinkbro.ru/terms/`
   - Authorized domain: `tinkbro.ru`
3. В **Audience** нажмите **Publish app**, затем в **Verification Center**
   подготовьте и отправьте заявку на проверку OAuth. Не заявляйте права,
   которые NewsFlow не использует.

## Локальная проверка

Из папки `oauth-site` выполните:

```powershell
python -m http.server 4173
```

После этого откройте `http://127.0.0.1:4173/`,
`http://127.0.0.1:4173/privacy/` и `http://127.0.0.1:4173/terms/`.

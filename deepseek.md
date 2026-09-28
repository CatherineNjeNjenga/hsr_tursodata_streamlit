html = fetch_page(EPISODE_URLS[0])
rows, meta = parse_episode(html, EPISODE_URLS[0])
print(meta)
for r in rows[:3]:
    print(r)

Next step: expand the two collapsed spans in DevTools and tell me what's inside span 1 and span 2. That confirms whether we can capture a brand or category label from the page directly, or whether we need to infer it from the ShopMy URL.

# Схема базы данных (DEMO)

Все денежные поля — виртуальные «учебные единицы» (УЕ).

```
users
  id PK
  telegram_id  UNIQUE
  username
  created_at
  balance              -- УЕ (виртуальные)
  tier                 -- 1=info, 2=manual, 3=auto
  tier_expires_at
  total_trades
  level                -- bronze/silver/gold/platinum
  referred_by          -- telegram_id пригласившего
  referral_earnings
  sound_enabled
  auto_turbo

trades                 -- сгенерированные DEMO-сделки
  id PK
  asset, volume, slippage, profit   -- profit может быть отрицательным
  state                -- analyzing -> open -> accepted -> executing -> completed | missed
  created_at, analyze_until, open_until
  is_demo = true

user_trades            -- принятые пользователем сделки
  id PK
  user_id FK -> users
  trade_id FK -> trades
  accepted_at
  accept_latency_ms    -- для таблицы лидеров «Скорость»
  realized_profit

transactions
  id PK
  user_id FK -> users
  type   -- deposit_demo|subscription|boost|turbo|trade_profit|referral_bonus|withdraw_demo|admin_adjust
  amount -- знаковая, УЕ
  note
  created_at

boost_purchases
  id PK, user_id FK, price, created_at

admin_logs
  id PK, admin_id, action, detail, created_at
```

## Связи

- `users 1—N transactions`
- `users 1—N user_trades N—1 trades`
- `users 1—N boost_purchases`

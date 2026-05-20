-- Остаток на balance_ledger по «своим» пополнениям (не bonus_admin), в копейках.
-- Выполнить на продакшен-БД. username может быть NULL.
-- Строки ledger без payment_id не попадают в выборку: при необходимости проверьте их отдельно.

SELECT
  u.telegram_id,
  u.username,
  SUM(bl.amount_cents) AS remaining_purchased_cents,
  ROUND(SUM(bl.amount_cents)::numeric / 100, 2) AS remaining_purchased_rub
FROM balance_ledger bl
JOIN users u ON u.telegram_id = bl.user_id
JOIN payments p ON p.id = bl.payment_id
WHERE bl.amount_cents > 0
  AND p.kind IS DISTINCT FROM 'bonus_admin'
GROUP BY u.telegram_id, u.username
HAVING SUM(bl.amount_cents) > 0
ORDER BY remaining_purchased_cents DESC;

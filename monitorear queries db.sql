SELECT id, user, db, time, state, info
FROM information_schema.processlist
WHERE command != 'Sleep'
ORDER BY time DESC;

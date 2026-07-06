SELECT id, user, db, time, state, info
FROM information_schema.processlist
WHERE command != 'Sleep' and time >= 0 and info not like '%information_schema%'
ORDER BY time DESC;

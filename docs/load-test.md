# Load test

Run on Nov 11, 2026 against the live site (Render free plan: 0.1 CPU, 512 MB, one process), from one machine about 350 ms
away. Read-only GET requests only, so it used no Pinecone allowance and created no data. Each level ran for about 12 seconds.

```
health: /api/health
users     ok  err   req/s  p50 ms  p95 ms
    1     26    0     2.1     362    1040
    5    111    0     8.9     427    1137
   10    232    0    18.4     434     996
   25    467    0    34.0     540    1465
   50    655    0    48.2     679    2228

overview: /api/repos/<demo repository>/overview   (signed in to the read-only demo)
users     ok  err   req/s  p50 ms  p95 ms
    1     20    0     1.6     475    2130
    5     95    0     7.0     527    1337
   10    110    0     8.1    1021    2050
   25    123    0     8.5    2624    4342
   50    132    0     7.5    5330    9875
```

**Reading it:** without database or analysis work the server keeps scaling to 50 users. A real page (session check, ownership
check, the cached commit history and the analytics) levels off at about 8 per second: that's the tenth of a CPU. Past about 10
users at once, extra requests wait in line, so the median time grows with the number of users, but none failed. The next
step would be more CPU (a paid instance) and several worker processes; caching each repository's analytics would also help,
since they only change on a re-sync.

The script is plain Python with httpx and asyncio: each simulated user sends a request, waits for the answer and sends the next.

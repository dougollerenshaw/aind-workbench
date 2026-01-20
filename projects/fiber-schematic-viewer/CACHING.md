# Caching Implementation

## Overview

Added file-based caching to dramatically speed up repeated queries to the metadata service.

## Performance

- **First query (cache miss):** ~30-40 seconds (queries metadata service)
- **Cached queries (cache hit):** < 0.1 seconds (reads from disk)
- **Cache TTL:** 1 week by default (configurable)

## How It Works

1. **Cache Check:** Before querying metadata service, check if cached data exists and is not expired
2. **Cache Miss:** Query metadata service, then save result to cache
3. **Cache Hit:** Return cached data immediately

## Configuration

```bash
# Use default cache settings (1 week TTL)
python app.py

# Custom cache directory and TTL
python app.py --cache-dir /tmp/procedures_cache --cache-ttl 24
```

Options:
- `--cache-dir`: Directory to store cached procedures (default: `.cache/procedures`)
- `--cache-ttl`: Cache time-to-live in hours (default: 168 = 1 week)

## Cache Structure

```
.cache/procedures/
  ├── 775741.json    # Cached procedures for subject 775741
  ├── 804434.json    # Cached procedures for subject 804434
  └── ...
```

Each file contains the full procedures JSON response from the metadata service.

## Cache Invalidation

The cache automatically expires after the TTL period. To manually clear the cache:

```bash
# Clear all cached procedures
rm -rf .cache/procedures/

# Clear specific subject
rm .cache/procedures/775741.json
```

## Why File-Based?

- **Persistent:** Survives server restarts
- **Simple:** No external dependencies (Redis, Memcached)
- **Transparent:** Easy to inspect cached data
- **Sufficient:** Procedures data doesn't change frequently

## Trade-offs

**Pros:**
- Dramatically faster for repeated queries
- Reduces load on metadata service
- Persists across restarts

**Cons:**
- Stale data possible (mitigated by TTL)
- Disk space usage (minimal - ~10KB per subject)
- Manual cache clearing needed if procedures are updated

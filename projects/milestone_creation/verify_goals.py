import json

with open("q3_goals.json", "r") as f:
    goals = json.load(f)

print(f"Total goals: {len(goals)}")

platforms = set(g["platform"] for g in goals)
print(f"\nPlatforms: {platforms}")

print("\nSample goals by platform:")
for platform in sorted(platforms):
    platform_goals = [g for g in goals if g["platform"] == platform]
    print(f"\n{platform} ({len(platform_goals)} goals):")
    for g in platform_goals[:3]:
        print(f'  - {g["title"]}')

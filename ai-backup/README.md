# AI Generation Backup CLI
#
# This is a standalone CLI for AI-powered card generation. It is NOT used by
# the YGO-Script or YGO-Desc skills — those skills use Claude Code directly.
# Run this CLI manually when you need batch processing or external AI generation.
#
# Usage:
#   bun ai-backup/ai_cli.py generate --name "Dark Magician" --desc "Once per turn..."
#   bun ai-backup/ai_cli.py parse "卡名：暗黑骑士 效果：一回合一次..."
#   bun ai-backup/ai_cli.py repair -s script.lua
#   bun ai-backup/ai_cli.py batch --db-path cards.cdb -i "add once per turn limit"

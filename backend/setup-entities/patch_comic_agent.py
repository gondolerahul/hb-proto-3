"""
Patch script to fix the comic_panel_generator entity in the database.

Fixes:
  1. comic_panel_generator - prompt_template uses {{Write Image Generation Prompts}}
     which doesn't exist in its context. Changed to {{Create Story & Characters}} 
     which is the actual key holding the image prompts.
  2. comic_panel_generator - context_policy preserve_keys updated to include 
     the real context keys.
  3. image_generation_skill - context_policy preserve_keys updated similarly.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from src.common.database import AsyncSessionLocal
from src.ai.models import HierarchicalEntity


async def patch_entities():
    async with AsyncSessionLocal() as session:
        # ------------------------------------------------------------------
        # Patch comic_panel_generator
        # ------------------------------------------------------------------
        result = await session.execute(
            select(HierarchicalEntity).where(
                HierarchicalEntity.name == "comic_panel_generator"
            )
        )
        generators = result.scalars().all()

        if not generators:
            print("ERROR: comic_panel_generator entity not found in database!")
            return

        for gen in generators:
            print(f"Patching comic_panel_generator (id={gen.id})...")

            # Update planning (prompt_template)
            import copy
            new_planning = copy.deepcopy(gen.planning or {})
            steps = new_planning.get("static_plan", {}).get("steps", [])

            for step in steps:
                if step.get("step_id") == "generate_panels" or step.get("name") == "Generate Comic Panel Images":
                    old_tpl = step.get("target", {}).get("prompt_template", "")
                    new_tpl = (
                        "Here are the 6 panel image prompts (JSON array).\n"
                        "Look for the prompts in the context under 'Create Story & Characters' or 'create_story':\n\n"
                        "Image Generation Prompts: {{Create Story & Characters}}\n\n"
                        "If the above is empty, check: {{create_story}}\n\n"
                        "Using the panel prompts above, call the image_generation tool ONCE for EACH of the 6 panels "
                        "using model_name='gemini-3-pro-image-preview'. "
                        "Make all 6 tool calls, then output a JSON array with panel_number, image_path (from tool result), "
                        "and dialogue for each panel. Do NOT stop after 1 panel — generate ALL 6."
                    )
                    step.setdefault("target", {})["prompt_template"] = new_tpl
                    print(f"  ✓ Updated prompt_template (was: {old_tpl[:80]}...)")

            gen.planning = new_planning

            # Update logic_gate context_policy preserve_keys
            new_logic_gate = copy.deepcopy(gen.logic_gate or {})
            ctx_policy = new_logic_gate.get("context_policy", {})
            ctx_policy["preserve_keys"] = [
                "Create Story & Characters",
                "create_story",
                "Write Image Generation Prompts",
                "write_image_prompts",
            ]
            new_logic_gate["context_policy"] = ctx_policy
            gen.logic_gate = new_logic_gate

            # Flag dirty so SQLAlchemy picks up the JSONB change
            from sqlalchemy.orm.attributes import flag_modified
            flag_modified(gen, "planning")
            flag_modified(gen, "logic_gate")

            print(f"  ✓ Updated context_policy.preserve_keys")

        # ------------------------------------------------------------------
        # Patch image_generation_skill
        # ------------------------------------------------------------------
        result2 = await session.execute(
            select(HierarchicalEntity).where(
                HierarchicalEntity.name == "image_generation_skill"
            )
        )
        skills = result2.scalars().all()

        if not skills:
            print("WARNING: image_generation_skill entity not found.")
        else:
            for skill in skills:
                print(f"Patching image_generation_skill (id={skill.id})...")
                new_logic_gate = copy.deepcopy(skill.logic_gate or {})
                ctx_policy = new_logic_gate.get("context_policy", {})
                ctx_policy["preserve_keys"] = [
                    "Create Story & Characters",
                    "create_story",
                    "Write Image Generation Prompts",
                    "write_image_prompts",
                    "Design Characters & Story",
                    "design_characters_story",
                ]
                new_logic_gate["context_policy"] = ctx_policy
                skill.logic_gate = new_logic_gate

                from sqlalchemy.orm.attributes import flag_modified
                flag_modified(skill, "logic_gate")
                print(f"  ✓ Updated context_policy.preserve_keys")

        await session.commit()
        print("\n✅ All patches applied successfully!")


if __name__ == "__main__":
    asyncio.run(patch_entities())

"""
Setup script for Children's Comic Strip Agent hierarchical entities.
Creates all entities (1 PROCESS, 3 AGENTS, 7 SKILLS, 10 ACTIONS) in the database.

Architecture:
  PROCESS: comic_strip_process
    AGENT 1: topic_research_agent       -> researches topic for child-appropriate content
    AGENT 2: visual_story_agent         -> designs characters and story panels
    AGENT 3: comic_production_agent     -> generates images and assembles the final PDF

Tools used:
  - web_search       : research child-appropriate topic content
  - scraper_tool     : scrape educational details about the topic
  - image_generation : generate comic panel images (model: gemini-3-pro-image-preview)
  - file_writer      : save intermediate story scripts/layouts
  - pdf_generator    : produce the final comic strip PDF

Image Generation Model: gemini-3-pro-image-preview
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from sqlalchemy.ext.asyncio import AsyncSession
from src.common.database import AsyncSessionLocal
from src.ai.models import HierarchicalEntity
from src.auth.models import Company
from sqlalchemy import select
from uuid import uuid4


# ---------------------------------------------------------------------------
# LEVEL 4 – ACTIONS
# ---------------------------------------------------------------------------

async def create_action_entities(session: AsyncSession, company_id):
    """Create all ACTION level entities (Level 4)."""
    print("Creating ACTION entities...")
    actions = {}

    # ------------------------------------------------------------------
    # ACTION 1: Topic Analyzer
    # ------------------------------------------------------------------
    actions["topic_analyzer"] = HierarchicalEntity(
        id=uuid4(),
        company_id=company_id,
        type="ACTION",
        name="topic_analyzer",
        display_name="Topic Analyzer",
        description="Analyzes the given topic and produces child-friendly research questions and web search queries suited for a children's comic.",
        tags=["analysis", "planning", "comic"],
        identity={
            "system_prompt": (
                "You are a creative children's content specialist. "
                "Given a topic, your job is to:\n"
                "1. Identify 3-5 fun, educational facts about the topic suitable for children aged 6-12.\n"
                "2. Suggest the GENRE of the comic (adventure, comedy, mystery, fantasy, science).\n"
                "3. Generate 3 web search queries to gather child-friendly, accurate information.\n"
                "4. Suggest a catchy comic title.\n\n"
                "Output valid JSON:\n"
                "{\n"
                "  \"comic_title\": \"...\",\n"
                "  \"genre\": \"...\",\n"
                "  \"key_facts\": [\"fact1\", \"fact2\", ...],\n"
                "  \"search_queries\": [\"query1\", \"query2\", \"query3\"]\n"
                "}"
            )
        },
        planning={
            "static_plan": {
                "enabled": True,
                "steps": [{
                    "step_id": "analyze",
                    "order": 1,
                    "name": "Analyze Topic",
                    "type": "THOUGHT",
                    "target": {
                        "prompt_template": (
                            "Topic: {{input}}\n\n"
                            "Analyze this topic for a children's comic strip. "
                            "Output JSON with comic_title, genre, key_facts (array), "
                            "and search_queries (array of 3 web search strings)."
                        )
                    },
                    "required": True
                }]
            }
        },
        logic_gate={
            "reasoning_config": {
                "model_provider": "google",
                "model_name": "gemini-3-flash-preview",
                "temperature": 0.6,
                "reasoning_mode": "CHAIN_OF_THOUGHT"
            }
        },
        governance={"timeout_ms": 30000}
    )

    # ------------------------------------------------------------------
    # ACTION 2: Web Research Action
    # ------------------------------------------------------------------
    actions["web_research_action"] = HierarchicalEntity(
        id=uuid4(),
        company_id=company_id,
        type="ACTION",
        name="web_research_action",
        display_name="Web Research Action",
        description="Executes web searches to gather child-appropriate factual content about the comic topic.",
        tags=["search", "web", "research"],
        identity={
            "system_prompt": (
                "You are a children's educational researcher. "
                "For each search query provided:\n"
                "1. Execute the web_search tool.\n"
                "2. Collect the top results.\n"
                "3. Note child-appropriate facts, stories, and trivia.\n\n"
                "Compile all findings into a structured list of facts and URLs."
            )
        },
        planning={
            "static_plan": {
                "enabled": True,
                "steps": [{
                    "step_id": "search",
                    "order": 1,
                    "name": "Execute Web Searches",
                    "type": "ACTION",
                    "target": {
                        "prompt_template": (
                            "Search queries: {{input}}\n\n"
                            "Use the web_search tool for each query. "
                            "Collect child-appropriate facts. "
                            "Return a JSON array of {fact, source_url} objects."
                        )
                    },
                    "required": True
                }]
            }
        },
        capabilities={"tools": [{"tool_id": "web_search"}]},
        logic_gate={
            "reasoning_config": {
                "model_provider": "google",
                "model_name": "gemini-3-flash-preview",
                "temperature": 0.2,
                "reasoning_mode": "REACT"
            }
        },
        governance={"timeout_ms": 60000}
    )

    # ------------------------------------------------------------------
    # ACTION 3: Content Scraper Action
    # ------------------------------------------------------------------
    actions["content_scraper_action"] = HierarchicalEntity(
        id=uuid4(),
        company_id=company_id,
        type="ACTION",
        name="content_scraper_action",
        display_name="Content Scraper Action",
        description="Scrapes educational web pages to extract detailed child-friendly content about the topic.",
        tags=["scraping", "content", "education"],
        identity={
            "system_prompt": (
                "You are a content extraction specialist for children's media. "
                "For each URL:\n"
                "1. Use the scraper_tool to extract content.\n"
                "2. Filter for age-appropriate (6-12) information.\n"
                "3. Extract fun facts, stories, and interesting details.\n"
                "4. Ignore adult themes, violence, or complex political content.\n\n"
                "Return structured educational content ready for a comic script."
            )
        },
        planning={
            "static_plan": {
                "enabled": True,
                "steps": [{
                    "step_id": "scrape",
                    "order": 1,
                    "name": "Scrape Educational Content",
                    "type": "ACTION",
                    "target": {
                        "prompt_template": (
                            "URLs to scrape: {{input}}\n\n"
                            "Use the scraper_tool on each URL. Extract child-appropriate "
                            "educational content. Return a JSON list of {content, url} objects."
                        )
                    },
                    "required": True
                }]
            }
        },
        capabilities={"tools": [{"tool_id": "scraper_tool"}]},
        logic_gate={
            "reasoning_config": {
                "model_provider": "google",
                "model_name": "gemini-3-flash-preview",
                "temperature": 0.1,
                "reasoning_mode": "REACT"
            }
        },
        governance={"timeout_ms": 90000}
    )

    # ------------------------------------------------------------------
    # ACTION 4: Character & Story Designer
    # ------------------------------------------------------------------
    actions["character_story_designer"] = HierarchicalEntity(
        id=uuid4(),
        company_id=company_id,
        type="ACTION",
        name="character_story_designer",
        display_name="Character & Story Designer",
        description="Creates vivid, memorable child-friendly characters and a 6-panel comic storyline from the researched topic.",
        tags=["character", "story", "design"],
        identity={
            "system_prompt": (
                "You are a world-class children's comic book writer and character designer. "
                "Your job is to create:\n\n"
                "CHARACTERS (2-3 main characters):\n"
                "- Give each character a fun name, personality, and visual appearance description.\n"
                "- Characters should be relatable to children (animals, kids, friendly robots, etc.).\n"
                "- Each character must have a distinctive look describable for image generation.\n\n"
                "STORY (6 panels):\n"
                "- Panel 1: Set the scene and introduce characters.\n"
                "- Panel 2: The adventure/problem begins.\n"
                "- Panel 3: Characters explore/investigate.\n"
                "- Panel 4: A challenge or funny twist.\n"
                "- Panel 5: Discovery or resolution.\n"
                "- Panel 6: Happy ending with a fun educational takeaway.\n\n"
                "Output valid JSON:\n"
                "{\n"
                "  \"characters\": [{\"name\": \"\", \"description\": \"\", \"appearance\": \"\"}],\n"
                "  \"panels\": [\n"
                "    {\"panel_number\": 1, \"scene\": \"\", \"dialogue\": \"\", \"action\": \"\"}\n"
                "  ]\n"
                "}"
            )
        },
        planning={
            "static_plan": {
                "enabled": True,
                "steps": [{
                    "step_id": "design",
                    "order": 1,
                    "name": "Design Characters and Story",
                    "type": "THOUGHT",
                    "target": {
                        "prompt_template": (
                            "Topic facts and research: {{input}}\n\n"
                            "Create 2-3 memorable child-friendly characters and a 6-panel comic story "
                            "incorporating the educational facts. Make it fun, colourful, and engaging. "
                            "Output as JSON with 'characters' and 'panels' arrays."
                        )
                    },
                    "required": True
                }]
            }
        },
        logic_gate={
            "reasoning_config": {
                "model_provider": "google",
                "model_name": "gemini-3-flash-preview",
                "temperature": 0.8,
                "reasoning_mode": "CHAIN_OF_THOUGHT"
            }
        },
        governance={"timeout_ms": 60000}
    )

    # ------------------------------------------------------------------
    # ACTION 5: Image Prompt Writer
    # ------------------------------------------------------------------
    actions["image_prompt_writer"] = HierarchicalEntity(
        id=uuid4(),
        company_id=company_id,
        type="ACTION",
        name="image_prompt_writer",
        display_name="Image Prompt Writer",
        description="Writes highly detailed, optimised image generation prompts for each comic panel to produce vibrant, child-friendly artwork.",
        tags=["prompt", "image", "comic"],
        identity={
            "system_prompt": (
                "You are an expert AI image prompt engineer specialising in children's comic art. "
                "For each comic panel, craft a detailed image generation prompt that:\n\n"
                "STYLE REQUIREMENTS (always include these):\n"
                "- Art style: bright, vibrant children's comic book illustration\n"
                "- Colour palette: bold primary colours, high contrast, cheerful\n"
                "- Line art: thick clean outlines like a comic book\n"
                "- Panel border: include a comic panel border\n"
                "- Characters: cute, expressive, child-friendly\n"
                "- Background: detailed, colourful, relevant to scene\n"
                "- Text space: leave space at bottom for dialogue bubble\n"
                "- Resolution: high detail, sharp, professional comic illustration\n\n"
                "For each panel output:\n"
                "{\n"
                "  \"panel_number\": N,\n"
                "  \"image_prompt\": \"[detailed prompt]\",\n"
                "  \"dialogue\": \"[character dialogue for this panel]\"\n"
                "}\n\n"
                "Make each prompt ultra-detailed and specific. The quality of these prompts "
                "directly determines the quality of the final comic."
            )
        },
        planning={
            "static_plan": {
                "enabled": True,
                "steps": [{
                    "step_id": "write_prompts",
                    "order": 1,
                    "name": "Write Image Prompts",
                    "type": "THOUGHT",
                    "target": {
                        "prompt_template": (
                            "Comic story data: {{input}}\n\n"
                            "Write a detailed image generation prompt for EACH of the 6 comic panels. "
                            "Each prompt must specify the art style (bright children's comic), characters, "
                            "scene background, and actions. Return a JSON array of panel prompt objects."
                        )
                    },
                    "required": True
                }]
            }
        },
        logic_gate={
            "reasoning_config": {
                "model_provider": "google",
                "model_name": "gemini-3-flash-preview",
                "temperature": 0.7,
                "reasoning_mode": "CHAIN_OF_THOUGHT"
            }
        },
        governance={"timeout_ms": 45000}
    )

    # ------------------------------------------------------------------
    # ACTION 6: Comic Panel Image Generator
    # ------------------------------------------------------------------
    actions["comic_panel_generator"] = HierarchicalEntity(
        id=uuid4(),
        company_id=company_id,
        type="ACTION",
        name="comic_panel_generator",
        display_name="Comic Panel Image Generator",
        description="Generates all 6 comic panel images using the Gemini image generation model (gemini-3-pro-image-preview).",
        tags=["image_generation", "comic", "panels"],
        identity={
            "system_prompt": (
                "You are a comic panel image generation specialist using the image_generation tool.\n"
                "You will receive a JSON array of panel objects, each with a 'panel_number' and 'image_prompt'.\n\n"
                "YOUR TASK:\n"
                "For EACH panel (1 through 6), call the image_generation tool ONCE with:\n"
                "  - model_name: 'gemini-3-pro-image-preview'\n"
                "  - prompt: the panel's image_prompt value (exactly as given)\n\n"
                "After ALL 6 tool calls are complete and you have 6 image paths, output ONLY a JSON array like:\n"
                "[\n"
                "  {\"panel_number\": 1, \"image_path\": \"/path/to/panel_1.png\", \"dialogue\": \"...\"},\n"
                "  {\"panel_number\": 2, \"image_path\": \"/path/to/panel_2.png\", \"dialogue\": \"...\"},\n"
                "  ...\n"
                "]\n\n"
                "RULES:\n"
                "- Always use model_name='gemini-3-pro-image-preview' — no exceptions.\n"
                "- Call image_generation ONCE per panel — 6 calls total.\n"
                "- The 'image_path' in your final JSON must be the EXACT path returned by the tool.\n"
                "- DO NOT invent or guess image paths. Use only what the tool returns.\n"
                "- DO NOT produce your final JSON until you have completed all 6 tool calls."
            )
        },
        planning={
            "static_plan": {
                "enabled": True,
                "steps": [{
                    "step_id": "generate_panels",
                    "order": 1,
                    "name": "Generate Comic Panel Images",
                    "type": "ACTION",
                    "target": {
                        "prompt_template": (
                            "Here are the 6 panel image prompts (JSON array).\n"
                            "Look for the prompts in the context under 'Create Story & Characters' or 'create_story':\n\n"
                            "Image Generation Prompts: {{Create Story & Characters}}\n\n"
                            "If the above is empty, check: {{create_story}}\n\n"
                            "Using the panel prompts above, call the image_generation tool ONCE for EACH of the 6 panels "
                            "using model_name='gemini-3-pro-image-preview'. "
                            "Make all 6 tool calls, then output a JSON array with panel_number, image_path (from tool result), "
                            "and dialogue for each panel. Do NOT stop after 1 panel — generate ALL 6."
                        )
                    },
                    "required": True
                }]
            }
        },
        capabilities={"tools": [{"tool_id": "image_generation"}]},
        logic_gate={
            "reasoning_config": {
                "model_provider": "google",
                "model_name": "gemini-3-flash-preview",
                "temperature": 0.1,
                "reasoning_mode": "REACT"
            },
            "context_policy": {
                "type": "FULL",
                "summarize_threshold": 100000,  # Never summarise — image prompts MUST be preserved verbatim
                "preserve_keys": ["Create Story & Characters", "create_story", "Write Image Generation Prompts", "write_image_prompts"]
            }
        },
        governance={"timeout_ms": 600000}  # 10 minutes for 6 API image gen calls
    )

    # ------------------------------------------------------------------
    # ACTION 7: Comic Script Writer (for PDF markdown)
    # ------------------------------------------------------------------
    actions["comic_script_writer"] = HierarchicalEntity(
        id=uuid4(),
        company_id=company_id,
        type="ACTION",
        name="comic_script_writer",
        display_name="Comic Script Writer",
        description="Writes the full comic markdown script including title page, panel descriptions, dialogues, and a fun educational ending note for PDF generation.",
        tags=["script", "markdown", "comic"],
        identity={
            "system_prompt": (
                "You are a professional children's comic script writer. "
                "Your task is to write a complete, beautifully formatted markdown document for the comic strip. "
                "The document must include:\n\n"
                "1. **COVER PAGE**: Comic title (large), tagline, and a fun description.\n"
                "2. **MEET THE CHARACTERS**: Each character's name and fun personality blurb.\n"
                "3. **THE COMIC PANELS** (6 panels):\n"
                "   - Panel heading (e.g. 'Panel 1 – The Beginning')\n"
                "   - Scene description (vivid, colourful)\n"
                "   - Dialogue (formatted as character: 'speech')\n"
                "   - Image embed using the EXACT image_path from the generated panels: ![Panel N](image_path)\n"
                "     IMPORTANT: Use the ACTUAL image paths from 'Generate Comic Panel Images' — NOT placeholder paths.\n"
                "4. **FUN FACTS BOX**: 3-5 educational facts kids learn from this comic.\n"
                "5. **THE END** with an encouraging message for young readers.\n\n"
                "Make the language joyful, simple, and age-appropriate for 6-12 year olds. "
                "Use emojis sparingly to add fun. This is the script that becomes the final PDF."
            )
        },
        planning={
            "static_plan": {
                "enabled": True,
                "steps": [
                    {
                        "step_id": "write_script",
                        "order": 1,
                        "name": "Write Full Comic Script",
                        "type": "THOUGHT",
                        "target": {
                            "prompt_template": (
                                "Comic story data:\n"
                                "- Characters & story: {{Design Characters & Story}}\n"
                                "- Generated panel images (JSON with image_path for each panel): {{Generate Comic Panel Images}}\n"
                                "- All research context: {{input}}\n\n"
                                "Write the complete markdown comic script with cover page, character bios, "
                                "6 panels each with scene, dialogue, and the REAL ![Panel N](image_path) embed "
                                "using EXACTLY the image_path values from 'Generate Comic Panel Images' above, "
                                "fun facts, and a closing message. "
                                "Make it magical and age-appropriate for children 6-12."
                            )
                        },
                        "required": True
                    },
                    {
                        "step_id": "save_script",
                        "order": 2,
                        "name": "Save Comic Script",
                        "type": "ACTION",
                        "target": {
                            "tool_id": "file_writer",
                            "prompt_template": (
                                "Save the comic script to a file. "
                                "Use the file_writer tool with:\n"
                                "  filename: 'space_exploration_comic.md' (use the actual topic slug)\n"
                                "  content: the full markdown script from the previous step\n"
                                "  company_id and user_id are available in context.\n\n"
                                "Comic script to save:\n{{Write Full Comic Script}}"
                            )
                        },
                        "required": True
                    }
                ]
            }
        },
        capabilities={"tools": [{"tool_id": "file_writer"}]},
        logic_gate={
            "reasoning_config": {
                "model_provider": "google",
                "model_name": "gemini-3-flash-preview",
                "temperature": 0.75,
                "reasoning_mode": "CHAIN_OF_THOUGHT"
            },
            "context_policy": {
                "type": "FULL",
                "summarize_threshold": 100000,
                "preserve_keys": ["Generate Comic Panel Images", "generate_all_panels", "Design Characters & Story", "design_characters_story"]
            }
        },
        governance={"timeout_ms": 90000}
    )

    # ------------------------------------------------------------------
    # ACTION 8: Comic PDF Publisher
    # ------------------------------------------------------------------
    actions["comic_pdf_publisher"] = HierarchicalEntity(
        id=uuid4(),
        company_id=company_id,
        type="ACTION",
        name="comic_pdf_publisher",
        display_name="Comic PDF Publisher",
        description="Generates the final illustrated comic strip PDF from the markdown script using the pdf_generator tool. Saves to the assets folder.",
        tags=["pdf", "publish", "comic", "output"],
        identity={
            "system_prompt": (
                "You are a children's comic book PDF publisher. "
                "Your job is to produce the final, polished PDF of the comic strip:\n\n"
                "1. Take the complete markdown comic script.\n"
                "2. Call the pdf_generator tool with:\n"
                "   - content: the full markdown script\n"
                "   - title: the comic title (e.g. 'The Adventures of ...')\n"
                "   - filename: a clean filename like 'comic_strip_[topic]'\n"
                "   - author: 'HireBuddha Comic Studio'\n"
                "   - subject: 'Children's Educational Comic Strip'\n"
                "3. Return the path to the generated PDF.\n\n"
                "The PDF is the FINAL deliverable. Make sure the title and filename are creative and fun."
            )
        },
        planning={
            "static_plan": {
                "enabled": True,
                "steps": [{
                    "step_id": "publish_pdf",
                    "order": 1,
                    "name": "Generate Comic PDF",
                    "type": "ACTION",
                    "target": {
                        "prompt_template": (
                            "Comic markdown script: {{input}}\n\n"
                            "Use the pdf_generator tool to create the final comic PDF. "
                            "Set title to the comic's name, filename to 'comic_strip_[topic_slug]', "
                            "author to 'HireBuddha Comic Studio', subject to 'Children\\'s Educational Comic Strip'. "
                            "Return the pdf_path from the tool result."
                        )
                    },
                    "required": True
                }]
            }
        },
        capabilities={"tools": [{"tool_id": "pdf_generator"}]},
        logic_gate={
            "reasoning_config": {
                "model_provider": "google",
                "model_name": "gemini-3-flash-preview",
                "temperature": 0.1,
                "reasoning_mode": "REACT"
            }
        },
        governance={"timeout_ms": 120000}
    )

    for action in actions.values():
        session.add(action)

    await session.commit()
    print(f"✓ Created {len(actions)} ACTION entities")
    return actions


# ---------------------------------------------------------------------------
# LEVEL 3 – SKILLS
# ---------------------------------------------------------------------------

async def create_skill_entities(session: AsyncSession, company_id, actions):
    """Create all SKILL level entities (Level 3)."""
    print("Creating SKILL entities...")
    skills = {}

    # ------------------------------------------------------------------
    # SKILL 1: Topic Research Skill
    # ------------------------------------------------------------------
    skills["topic_research_skill"] = HierarchicalEntity(
        id=uuid4(),
        company_id=company_id,
        type="SKILL",
        name="topic_research_skill",
        display_name="Topic Research Skill",
        description="Analyzes the comic topic, generates search queries, searches the web, and scrapes educational content suitable for children.",
        tags=["research", "education", "web"],
        identity={
            "system_prompt": (
                "You are a children's educational research coordinator. "
                "Your skill combines topic analysis, web search, and content scraping "
                "to gather high-quality, age-appropriate material for a children's comic strip."
            )
        },
        planning={
            "static_plan": {
                "enabled": True,
                "steps": [
                    {
                        "step_id": "analyze_topic",
                        "order": 1,
                        "name": "Analyze Topic",
                        "type": "CHILD_ENTITY_INVOCATION",
                        "target": {"entity_id": str(actions["topic_analyzer"].id)},
                        "required": True
                    },
                    {
                        "step_id": "web_research",
                        "order": 2,
                        "name": "Web Research",
                        "type": "CHILD_ENTITY_INVOCATION",
                        "target": {
                            "entity_id": str(actions["web_research_action"].id),
                            "input_dependencies": ["analyze_topic"]
                        },
                        "required": True
                    },
                    {
                        "step_id": "scrape_content",
                        "order": 3,
                        "name": "Scrape Educational Content",
                        "type": "CHILD_ENTITY_INVOCATION",
                        "target": {
                            "entity_id": str(actions["content_scraper_action"].id),
                            "input_dependencies": ["web_research"]
                        },
                        "required": False
                    }
                ]
            }
        },
        logic_gate={
            "reasoning_config": {
                "model_provider": "google",
                "model_name": "gemini-3-flash-preview",
                "temperature": 0.3,
                "reasoning_mode": "REACT"
            }
        },
        governance={"timeout_ms": 180000}
    )

    # ------------------------------------------------------------------
    # SKILL 2: Story & Character Design Skill
    # ------------------------------------------------------------------
    skills["story_character_skill"] = HierarchicalEntity(
        id=uuid4(),
        company_id=company_id,
        type="SKILL",
        name="story_character_skill",
        display_name="Story & Character Design Skill",
        description="Creates memorable characters and a 6-panel comic storyline from researched content, then writes detailed image generation prompts for each panel.",
        tags=["story", "character", "design", "prompts"],
        identity={
            "system_prompt": (
                "You are a master children's storyteller and visual designer. "
                "You transform educational research into an exciting characters and story, "
                "then craft precision image prompts that will generate stunning comic panel artwork."
            )
        },
        planning={
            "static_plan": {
                "enabled": True,
                "steps": [
                    {
                        "step_id": "design_characters_story",
                        "order": 1,
                        "name": "Design Characters & Story",
                        "type": "CHILD_ENTITY_INVOCATION",
                        "target": {"entity_id": str(actions["character_story_designer"].id)},
                        "required": True
                    },
                    {
                        "step_id": "write_image_prompts",
                        "order": 2,
                        "name": "Write Image Generation Prompts",
                        "type": "CHILD_ENTITY_INVOCATION",
                        "target": {
                            "entity_id": str(actions["image_prompt_writer"].id),
                            "input_dependencies": ["design_characters_story"]
                        },
                        "required": True
                    }
                ]
            }
        },
        logic_gate={
            "reasoning_config": {
                "model_provider": "google",
                "model_name": "gemini-3-flash-preview",
                "temperature": 0.7,
                "reasoning_mode": "CHAIN_OF_THOUGHT"
            }
        },
        governance={"timeout_ms": 120000}
    )

    # ------------------------------------------------------------------
    # SKILL 3: Image Generation Skill
    # ------------------------------------------------------------------
    skills["image_generation_skill"] = HierarchicalEntity(
        id=uuid4(),
        company_id=company_id,
        type="SKILL",
        name="image_generation_skill",
        display_name="Comic Image Generation Skill",
        description="Generates all 6 comic panel images using the Gemini image generation model (gemini-3-pro-image-preview) from detailed prompts.",
        tags=["image", "generation", "panels", "gemini"],
        identity={
            "system_prompt": (
                "You are an AI comic panel illustration director. "
                "You orchestrate the generation of all 6 comic panels using the "
                "gemini-3-pro-image-preview model to produce vibrant, child-friendly artwork."
            )
        },
        planning={
            "static_plan": {
                "enabled": True,
                "steps": [{
                    "step_id": "generate_all_panels",
                    "order": 1,
                    "name": "Generate All Comic Panels",
                    "type": "CHILD_ENTITY_INVOCATION",
                    "target": {"entity_id": str(actions["comic_panel_generator"].id)},
                    "required": True
                }]
            }
        },
        capabilities={"tools": [{"tool_id": "image_generation"}]},
        logic_gate={
            "reasoning_config": {
                "model_provider": "google",
                "model_name": "gemini-3-flash-preview",
                "temperature": 0.1,
                "reasoning_mode": "REACT"
            },
            "context_policy": {
                "type": "FULL",
                "summarize_threshold": 100000,
                "preserve_keys": ["Create Story & Characters", "create_story", "Write Image Generation Prompts", "write_image_prompts", "Design Characters & Story", "design_characters_story"]
            }
        },
        governance={"timeout_ms": 600000}  # 10 min for full image generation
    )

    # ------------------------------------------------------------------
    # SKILL 4: Comic Assembly & PDF Skill
    # ------------------------------------------------------------------
    skills["comic_assembly_skill"] = HierarchicalEntity(
        id=uuid4(),
        company_id=company_id,
        type="SKILL",
        name="comic_assembly_skill",
        display_name="Comic Assembly & PDF Skill",
        description="Assembles the final comic script from generated images, writes the full markdown, and publishes the PDF to the assets folder.",
        tags=["assembly", "pdf", "script", "publish"],
        identity={
            "system_prompt": (
                "You are a comic book production manager. "
                "You combine all generated assets (images, dialogues, facts) into a cohesive, "
                "beautifully written markdown script, then produce the final PDF comic strip."
            )
        },
        planning={
            "static_plan": {
                "enabled": True,
                "steps": [
                    {
                        "step_id": "write_comic_script",
                        "order": 1,
                        "name": "Write Comic Markdown Script",
                        "type": "CHILD_ENTITY_INVOCATION",
                        "target": {"entity_id": str(actions["comic_script_writer"].id)},
                        "required": True
                    },
                    {
                        "step_id": "publish_pdf",
                        "order": 2,
                        "name": "Publish Comic PDF",
                        "type": "CHILD_ENTITY_INVOCATION",
                        "target": {
                            "entity_id": str(actions["comic_pdf_publisher"].id),
                            "input_dependencies": ["write_comic_script"]
                        },
                        "required": True
                    }
                ]
            }
        },
        capabilities={"tools": [{"tool_id": "pdf_generator"}, {"tool_id": "file_writer"}]},
        logic_gate={
            "reasoning_config": {
                "model_provider": "google",
                "model_name": "gemini-3-flash-preview",
                "temperature": 0.3,
                "reasoning_mode": "CHAIN_OF_THOUGHT"
            }
        },
        governance={"timeout_ms": 180000}
    )

    for skill in skills.values():
        session.add(skill)

    await session.commit()
    print(f"✓ Created {len(skills)} SKILL entities")
    return skills


# ---------------------------------------------------------------------------
# LEVEL 2 – AGENTS
# ---------------------------------------------------------------------------

async def create_agent_entities(session: AsyncSession, company_id, skills):
    """Create all AGENT level entities (Level 2)."""
    print("Creating AGENT entities...")
    agents = {}

    # ------------------------------------------------------------------
    # AGENT 1: Topic Research Agent
    # ------------------------------------------------------------------
    agents["topic_research_agent"] = HierarchicalEntity(
        id=uuid4(),
        company_id=company_id,
        type="AGENT",
        name="topic_research_agent",
        display_name="Topic Research Agent",
        description=(
            "Researches any given topic to extract child-appropriate educational content "
            "suitable for a children's comic strip. Uses web search and content scraping."
        ),
        tags=["research", "education", "children", "web"],
        identity={
            "system_prompt": (
                "You are an expert children's educational content researcher. "
                "Your mission is to gather rich, accurate, age-appropriate (6-12 years) "
                "information about any topic for use in a children's comic strip.\n\n"
                "You must:\n"
                "- Find fun, surprising, and educational facts.\n"
                "- Identify child-relatable analogies and examples.\n"
                "- Avoid adult themes, violence, or complex political content.\n"
                "- Structure findings so they can become an engaging comic story.\n"
                "- Always prioritise accuracy: facts in children's media must be correct."
            ),
            "behavioral_constraints": [
                "Only gather age-appropriate content (suitable for 6-12 year olds)",
                "Always verify facts from at least 2 sources",
                "Flag any potentially sensitive content for human review",
                "Ensure cultural sensitivity and inclusivity in all content"
            ]
        },
        planning={
            "static_plan": {
                "enabled": True,
                "steps": [{
                    "step_id": "research_topic",
                    "order": 1,
                    "name": "Research Topic",
                    "type": "CHILD_ENTITY_INVOCATION",
                    "target": {"entity_id": str(skills["topic_research_skill"].id)},
                    "required": True
                }],
                "fallback_behavior": "ADAPTIVE"
            },
            "dynamic_planning": {
                "enabled": True,
                "planning_prompt": (
                    "Assess the gathered research. If educational facts are insufficient "
                    "(fewer than 3 solid facts) or content is not child-appropriate, "
                    "plan additional targeted searches with different keywords."
                ),
                "allowed_deviations": {
                    "can_add_steps": True,
                    "can_skip_optional_steps": True
                }
            },
            "loop_control": {"max_iterations": 3, "iteration_context_mode": "SUMMARIZED"}
        },
        logic_gate={
            "reasoning_config": {
                "model_provider": "google",
                "model_name": "gemini-3-flash-preview",
                "temperature": 0.4,
                "reasoning_mode": "REACT"
            },
            "context_policy": {"type": "FULL"},
            "review_mechanism": {
                "enabled": True,
                "review_prompt": (
                    "Check: 1) Are there at least 3 fun educational facts? "
                    "2) Is all content appropriate for ages 6-12? "
                    "3) Is the content accurate and from credible sources?"
                ),
                "on_failure": "RETRY"
            }
        },
        governance={"timeout_ms": 300000, "max_recursion_depth": 6},
        observability={"log_thoughts": True, "track_cost": True}
    )

    # ------------------------------------------------------------------
    # AGENT 2: Visual Story Agent
    # ------------------------------------------------------------------
    agents["visual_story_agent"] = HierarchicalEntity(
        id=uuid4(),
        company_id=company_id,
        type="AGENT",
        name="visual_story_agent",
        display_name="Visual Story Agent",
        description=(
            "Transforms researched content into a compelling 6-panel comic story with "
            "memorable characters and generates all comic panel images using Gemini image AI."
        ),
        tags=["story", "visual", "character", "image_generation"],
        identity={
            "system_prompt": (
                "You are a legendary children's comic book creator — part storyteller, "
                "part visual artist director. You transform dry facts into magical adventures.\n\n"
                "Your characters must be:\n"
                "- Memorable and relatable to children.\n"
                "- Visually distinctive (describable in image prompts).\n"
                "- Emotionally engaging with clear personalities.\n\n"
                "Your storyline must:\n"
                "- Weave educational facts naturally into the adventure.\n"
                "- Follow a clear 6-panel narrative arc.\n"
                "- Have a satisfying, positive ending.\n"
                "- Be funny, surprising, or heartwarming.\n\n"
                "Your image prompts must be:\n"
                "- Highly detailed and specific.\n"
                "- Consistent in art style across all panels.\n"
                "- Optimised for AI image generation quality.\n"
                "- Always specify: bright children's comic style, bold outlines, vibrant colours."
            ),
            "few_shot_examples": [{
                "scenario": "Topic: Dinosaurs",
                "ideal_response": (
                    "Characters: Rex (a friendly T-Rex who is actually tiny and shy), "
                    "Stella (a clever Triceratops who loves books). "
                    "Story: Rex and Stella discover a mysterious fossil that leads them "
                    "on a time-travel adventure to meet their ancestors, learning that "
                    "dinosaurs were warm-blooded and some had feathers!"
                )
            }],
            "behavioral_constraints": [
                "Maintain consistent character appearances across all 6 panel prompts",
                "Always use 'gemini-3-pro-image-preview' as the image generation model",
                "Ensure each panel advances the story meaningfully",
                "Keep dialogue short and punchy — max 2 speech bubbles per panel"
            ]
        },
        planning={
            "static_plan": {
                "enabled": True,
                "steps": [
                    {
                        "step_id": "create_story",
                        "order": 1,
                        "name": "Create Story & Characters",
                        "type": "CHILD_ENTITY_INVOCATION",
                        "target": {"entity_id": str(skills["story_character_skill"].id)},
                        "required": True
                    },
                    {
                        "step_id": "generate_images",
                        "order": 2,
                        "name": "Generate Comic Panel Images",
                        "type": "CHILD_ENTITY_INVOCATION",
                        "target": {
                            "entity_id": str(skills["image_generation_skill"].id),
                            "input_dependencies": ["create_story"]
                        },
                        "required": True
                    }
                ],
                "fallback_behavior": "ADAPTIVE"
            },
            "dynamic_planning": {
                "enabled": True,
                "planning_prompt": (
                    "Review the story and images. If any panel image failed generation, "
                    "retry with a simplified prompt. If the story lacks educational value, "
                    "plan a story revision step."
                ),
                "allowed_deviations": {"can_add_steps": True}
            }
        },
        logic_gate={
            "reasoning_config": {
                "model_provider": "google",
                "model_name": "gemini-3-flash-preview",
                "temperature": 0.6,
                "reasoning_mode": "CHAIN_OF_THOUGHT"
            },
            "context_policy": {"type": "FULL"},
            "review_mechanism": {
                "enabled": True,
                "review_prompt": (
                    "Verify: 1) Are all 6 panels described with vivid imagery? "
                    "2) Are character appearances consistent across prompts? "
                    "3) Were all 6 images successfully generated? "
                    "4) Does the story include educational facts naturally?"
                ),
                "on_failure": "RETRY"
            }
        },
        governance={"timeout_ms": 480000, "max_recursion_depth": 6},
        observability={"log_thoughts": True, "track_cost": True}
    )

    # ------------------------------------------------------------------
    # AGENT 3: Comic Production Agent
    # ------------------------------------------------------------------
    agents["comic_production_agent"] = HierarchicalEntity(
        id=uuid4(),
        company_id=company_id,
        type="AGENT",
        name="comic_production_agent",
        display_name="Comic Production Agent",
        description=(
            "Assembles the final comic strip: writes the full markdown script combining "
            "story, images and dialogues, then publishes it as a beautiful PDF."
        ),
        tags=["production", "pdf", "comic", "assembly"],
        identity={
            "system_prompt": (
                "You are the Chief Production Editor of the world's best children's comic studio. "
                "You take all creative assets and produce the final, polished comic strip PDF.\n\n"
                "Your PDF must feel like a real published comic book:\n"
                "- Professional cover page with title and tagline.\n"
                "- Clear, colourful character introductions.\n"
                "- 6 illustrated panels with crisp dialogue.\n"
                "- A 'Fun Facts' educational section.\n"
                "- An encouraging closing message.\n\n"
                "Quality standards:\n"
                "- Language level: fun and accessible for ages 6-12.\n"
                "- Tone: joyful, inspiring, educational.\n"
                "- Layout: clean, well-organised, visually guided.\n"
                "- The final PDF goes to the assets/comic_strips folder."
            ),
            "behavioral_constraints": [
                "Always include a 'Fun Facts' educational section in the PDF",
                "Keep all language at a reading level appropriate for ages 6-12",
                "The PDF filename must be descriptive and include the topic name",
                "Always include page numbers and the comic title in the header"
            ]
        },
        planning={
            "static_plan": {
                "enabled": True,
                "steps": [{
                    "step_id": "assemble_and_publish",
                    "order": 1,
                    "name": "Assemble Comic & Publish PDF",
                    "type": "CHILD_ENTITY_INVOCATION",
                    "target": {"entity_id": str(skills["comic_assembly_skill"].id)},
                    "required": True
                }],
                "fallback_behavior": "ADAPTIVE"
            },
            "dynamic_planning": {
                "enabled": True,
                "planning_prompt": (
                    "Review the generated PDF. If PDF generation failed, "
                    "attempt with simplified content. Ensure the file is saved to artifact folder."
                ),
                "allowed_deviations": {"can_add_steps": True}
            }
        },
        logic_gate={
            "reasoning_config": {
                "model_provider": "google",
                "model_name": "gemini-3-flash-preview",
                "temperature": 0.3,
                "reasoning_mode": "CHAIN_OF_THOUGHT"
            },
            "context_policy": {"type": "FULL"},
            "review_mechanism": {
                "enabled": True,
                "review_prompt": (
                    "Check: 1) Was the PDF successfully generated and saved? "
                    "2) Does it include all 6 panels? "
                    "3) Are images embedded correctly? "
                    "4) Is the educational fun-facts section present?"
                ),
                "on_failure": "RETRY"
            }
        },
        governance={"timeout_ms": 300000, "max_recursion_depth": 5},
        observability={"log_thoughts": True, "track_cost": True}
    )

    for agent in agents.values():
        session.add(agent)

    await session.commit()
    print(f"✓ Created {len(agents)} AGENT entities")
    return agents


# ---------------------------------------------------------------------------
# LEVEL 1 – PROCESS
# ---------------------------------------------------------------------------

async def create_process_entity(session: AsyncSession, company_id, agents):
    """Create the top-level PROCESS entity (Level 1)."""
    print("Creating PROCESS entity...")

    process = HierarchicalEntity(
        id=uuid4(),
        company_id=company_id,
        type="PROCESS",
        name="comic_strip_process",
        display_name="Children's Comic Strip Generator",
        description=(
            "The world's best AI-powered children's comic strip generator. "
            "Give it any topic and it will research educational content, create memorable characters, "
            "generate beautiful comic panel images using Gemini AI, and produce a print-ready PDF comic strip. "
            "The entire process is automated and produces a professionally formatted, "
            "illustrated comic suitable for children aged 6-12."
        ),
        tags=["comic", "children", "education", "pdf", "image_generation", "creative"],
        identity={
            "system_prompt": (
                "You are the master orchestrator of the world's most advanced children's comic strip AI. "
                "Your mission: transform ANY topic into a stunning, educational, illustrated comic strip for children.\n\n"
                "You coordinate three specialist agents:\n"
                "1. **Topic Research Agent** – Finds age-appropriate educational facts via web search.\n"
                "2. **Visual Story Agent** – Creates characters, storyline, and generates 6 comic panel images.\n"
                "3. **Comic Production Agent** – Assembles everything into a polished PDF comic strip.\n\n"
                "Your standards:\n"
                "- CREATIVITY: Make the comics fun, surprising, and visually stunning.\n"
                "- EDUCATION: Every comic must teach children something true and valuable.\n"
                "- SAFETY: All content must be 100% appropriate for children aged 6-12.\n"
                "- QUALITY: The final PDF must look like a professionally published comic book.\n\n"
                "You are creating the next generation of children's storytelling. "
                "Every comic you produce should spark curiosity and a love of learning."
            ),
            "behavioral_constraints": [
                "All content must be safe and appropriate for children aged 6-12",
                "Always use 'gemini-3-pro-image-preview' for image generation",
                "PDF must be saved to the artifact/assets directory",
                "Every comic must include at least 3 verifiable educational facts",
                "Image generation must succeed for all 6 panels before PDF creation",
                "Never generate content involving violence, adult themes, or fear-inducing imagery"
            ]
        },
        planning={
            "static_plan": {
                "enabled": True,
                "steps": [
                    {
                        "step_id": "step_1_research",
                        "order": 1,
                        "name": "Research Phase",
                        "description": "Research the topic and gather child-appropriate educational content",
                        "type": "CHILD_ENTITY_INVOCATION",
                        "target": {"entity_id": str(agents["topic_research_agent"].id)},
                        "required": True
                    },
                    {
                        "step_id": "step_2_visual_story",
                        "order": 2,
                        "name": "Visual Story Phase",
                        "description": "Create story, characters, and generate all 6 comic panel images",
                        "type": "CHILD_ENTITY_INVOCATION",
                        "target": {
                            "entity_id": str(agents["visual_story_agent"].id),
                            "input_dependencies": ["step_1_research"]
                        },
                        "required": True
                    },
                    {
                        "step_id": "step_3_production",
                        "order": 3,
                        "name": "Production Phase",
                        "description": "Assemble the full comic script and generate the final PDF",
                        "type": "CHILD_ENTITY_INVOCATION",
                        "target": {
                            "entity_id": str(agents["comic_production_agent"].id),
                            "input_dependencies": ["step_2_visual_story"]
                        },
                        "required": True
                    }
                ],
                "fallback_behavior": "ADAPTIVE"
            },
            "dynamic_planning": {
                "enabled": True,
                "planning_prompt": (
                    "Based on the topic complexity and initial research quality, "
                    "decide if additional research depth is needed. "
                    "For science topics: prioritise accuracy. "
                    "For historical topics: prioritise engaging storytelling. "
                    "For nature topics: prioritise visual richness and wonder."
                ),
                "constraints": [
                    "Always complete all 3 phases in order",
                    "Never skip image generation — visual appeal is critical",
                    "Always verify PDF was saved before reporting success"
                ],
                "reconciliation_strategy": "HYBRID",
                "allowed_deviations": {
                    "can_add_steps": True,
                    "can_skip_optional_steps": False,
                    "can_reorder_steps": False
                }
            },
            "loop_control": {
                "max_iterations": 2,
                "iteration_context_mode": "SUMMARIZED"
            }
        },
        logic_gate={
            "reasoning_config": {
                "model_provider": "google",
                "model_name": "gemini-3-flash-preview",
                "temperature": 0.5,
                "reasoning_mode": "CHAIN_OF_THOUGHT"
            },
            "context_policy": {"type": "FULL"}
        },
        capabilities={
            "context_engineering": {
                "context_priority": ["SYSTEM_PROMPT", "USER_INPUT", "STATIC_PLAN"]
            }
        },
        governance={
            "timeout_ms": 900000,   # 15 minutes – image generation takes time
            "max_recursion_depth": 12
        },
        io_contract={
            "input_schema": {
                "type": "object",
                "properties": {
                    "input": {
                        "type": "string",
                        "description": "The topic for the children's comic strip (e.g. 'Planets', 'Rainforest Animals', 'Ancient Egypt')"
                    },
                    "age_group": {
                        "type": "string",
                        "enum": ["6-8", "8-10", "10-12"],
                        "description": "Target age group for the comic (optional, defaults to 6-12)"
                    },
                    "style": {
                        "type": "string",
                        "enum": ["adventure", "comedy", "mystery", "fantasy", "science"],
                        "description": "Preferred comic genre style (optional)"
                    }
                },
                "required": ["input"]
            },
            "output_schema": {
                "type": "object",
                "properties": {
                    "pdf_path": {"type": "string", "description": "Path to the generated comic strip PDF"},
                    "comic_title": {"type": "string", "description": "Title of the generated comic"},
                    "panel_images": {"type": "array", "description": "List of generated panel image paths"},
                    "educational_facts": {"type": "array", "description": "Educational facts included in the comic"}
                }
            }
        },
        observability={
            "log_level": "INFO",
            "log_thoughts": True,
            "track_cost": True
        }
    )

    session.add(process)
    await session.commit()
    print("✓ Created PROCESS entity")
    return process


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# COMIC STRIP ENTITY NAMES — used for both cleanup and creation
# ---------------------------------------------------------------------------
COMIC_ENTITY_NAMES = [
    # PROCESS
    "comic_strip_process",
    # AGENTS
    "topic_research_agent", "visual_story_agent", "comic_production_agent",
    # SKILLS
    "topic_research_skill", "story_character_skill", "image_generation_skill", "comic_assembly_skill",
    # ACTIONS
    "topic_analyzer", "web_research_action", "content_scraper_action",
    "character_story_designer", "image_prompt_writer", "comic_panel_generator",
    "comic_script_writer", "comic_pdf_publisher",
]


async def cleanup_existing_entities(session: AsyncSession, company_id) -> int:
    """Delete ALL existing comic strip entities and their execution history.

    Uses a recursive CTE to find the entire run tree, then deletes
    all child log rows, all runs (leaf-first), then the entities.

    Returns the number of entity rows deleted.
    """
    from sqlalchemy import text

    print("🧹 Cleaning up existing comic strip entities...")

    names_sql = ", ".join(f"'{n}'" for n in COMIC_ENTITY_NAMES)

    # Step 1: find old entity IDs
    r = await session.execute(text(
        f"SELECT id FROM hierarchical_entities WHERE name IN ({names_sql})"
    ))
    entity_ids = [str(row[0]) for row in r.fetchall()]

    if not entity_ids:
        print("   Nothing to clean up – no existing entities found.\n")
        return 0

    print(f"   Found {len(entity_ids)} existing entity row(s).")
    id_list = ", ".join(f"'{i}'" for i in entity_ids)

    # Step 2: find ALL run IDs in trees rooted at these entities (recursive CTE)
    r2 = await session.execute(text(f"""
        WITH RECURSIVE run_tree AS (
            SELECT id FROM execution_runs WHERE entity_id IN ({id_list})
            UNION ALL
            SELECT er.id FROM execution_runs er
            JOIN run_tree rt ON er.parent_run_id = rt.id
        )
        SELECT id FROM run_tree
    """))
    all_run_ids = [str(row[0]) for row in r2.fetchall()]
    print(f"   Found {len(all_run_ids)} total execution run row(s) to remove.")

    if all_run_ids:
        run_id_list = ", ".join(f"'{i}'" for i in all_run_ids)

        # Step 3: delete all log child tables
        for tbl in ["llm_interaction_logs", "tool_interaction_logs",
                    "human_approvals", "usage_logs"]:
            try:
                res = await session.execute(
                    text(f"DELETE FROM {tbl} WHERE run_id IN ({run_id_list})")
                )
                if res.rowcount:
                    print(f"   Removed {res.rowcount} rows from {tbl}.")
            except Exception:
                pass  # table may not exist yet

        # Step 4: delete runs leaf-first (iterative to respect self-FK)
        remaining_runs = list(all_run_ids)
        for _pass in range(20):
            if not remaining_runs:
                break
            rlist = ", ".join(f"'{i}'" for i in remaining_runs)
            res = await session.execute(text(f"""
                DELETE FROM execution_runs
                WHERE id IN ({rlist})
                AND id NOT IN (
                    SELECT DISTINCT parent_run_id FROM execution_runs
                    WHERE parent_run_id IN ({rlist})
                )
                RETURNING id
            """))
            gone = {str(row[0]) for row in res.fetchall()}
            if not gone:
                break
            remaining_runs = [r for r in remaining_runs if r not in gone]

        await session.flush()

    # Step 5: delete the entities
    res = await session.execute(
        text(f"DELETE FROM hierarchical_entities WHERE id IN ({id_list}) RETURNING id")
    )
    deleted = res.rowcount
    await session.commit()
    print(f"   ✓ Deleted {deleted} entity row(s) and all associated data.\n")
    return deleted


async def main():
    """Main setup function. Cleans up duplicates first, then recreates all entities."""
    print("\n" + "=" * 65)
    print("  Children's Comic Strip Generator – Entity Setup")
    print("=" * 65 + "\n")

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Company).limit(1))
        company = result.scalar_one_or_none()

        if not company:
            print("❌ No company found in database. Please create a company first.")
            return

        print(f"Using company: {company.name} (ID: {company.id})\n")

        # ── Step 0: remove all existing comic strip entities (prevents duplicates) ──
        await cleanup_existing_entities(session, company.id)

        # ── Build bottom-up: ACTIONS → SKILLS → AGENTS → PROCESS ──
        actions = await create_action_entities(session, company.id)
        skills  = await create_skill_entities(session, company.id, actions)
        agents  = await create_agent_entities(session, company.id, skills)
        process = await create_process_entity(session, company.id, agents)

        print("\n" + "=" * 65)
        print("✅ Successfully created all entities!")
        print("=" * 65)
        print(f"\nEntity Summary:")
        print(f"  PROCESS  : 1  – {process.display_name}")
        print(f"  AGENTS   : 3  – Topic Research, Visual Story, Comic Production")
        print(f"  SKILLS   : 4  – Topic Research, Story Design, Image Gen, Assembly")
        print(f"  ACTIONS  : 8  – Analyzer, Web Search, Scraper, Story Designer,")
        print(f"                   Prompt Writer, Panel Generator, Script Writer, PDF Publisher")
        print(f"\nProcess Entity ID : {process.id}")
        print(f"Process Name      : {process.display_name}")
        print(f"\nImage Model Used  : gemini-3-pro-image-preview")
        print(f"PDF Output Folder : backend/artifact/[company_id]/[user_id]/")
        print(f"\n▶ Navigate to Entity Library → 'Children's Comic Strip Generator'")
        print(f"▶ Enter any topic (e.g. 'Volcanoes', 'Space Exploration', 'Dinosaurs')")
        print("=" * 65 + "\n")


if __name__ == "__main__":
    asyncio.run(main())

"""
Agent Context Loader for streaming sessions.

Loads agent configuration and conversation history for each session.
Integrates with existing HierarchicalEntity system.
"""
import logging
from uuid import UUID
from typing import Optional, Dict, Any, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from src.ai.models import HierarchicalEntity
from src.voice.models import ConversationHistory
from src.config.models import IntegrationRegistry
from src.common.security import decrypt_api_key

logger = logging.getLogger(__name__)


class AgentContext:
    """Container for agent configuration and context."""
    
    def __init__(
        self,
        agent_id: UUID,
        system_instruction: str,
        conversation_history: List[Dict[str, Any]],
        llm_config: Dict[str, Any],
        capabilities: Dict[str, Any],
        tools: Optional[List] = None,
        api_key: Optional[str] = None,
        voice_config: Optional[Any] = None,   # VoiceConfig from AgentPersona
        live_model: Optional[str] = None,      # Per-agent Live model override
    ):
        self.agent_id = agent_id
        self.system_instruction = system_instruction
        self.conversation_history = conversation_history
        self.llm_config = llm_config
        self.capabilities = capabilities
        self.tools = tools or []
        self.api_key = api_key
        # P2.4 — voice / model overrides from AgentPersona
        self.voice_config = voice_config
        self.task_type = "speech_to_speech"


class AgentContextLoader:
    """Loads agent configuration for streaming sessions."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def load_agent_for_session(
        self,
        agent_id: UUID,
        customer_id: UUID,
        channel: str = "voice"
    ) -> AgentContext:
        """
        Load agent context for a streaming session.
        """
        # 1. Load HierarchicalEntity from database
        result = await self.db.execute(
            select(HierarchicalEntity).where(HierarchicalEntity.id == agent_id)
        )
        entity = result.scalar_one_or_none()
        
        if not entity:
            raise ValueError(f"Agent not found: {agent_id}")
        
        # 2. P2.4 — Resolve AgentPersona for dynamic system prompt + VoiceConfig
        from src.ai.persona_service import PersonaService, build_system_prompt_from_persona
        persona_svc = PersonaService(self.db)
        persona = await persona_svc.get_persona_from_entity(entity)
        
        if persona:
            system_instruction = build_system_prompt_from_persona(persona)
            voice_config = persona.voice
        else:
            # Legacy fallback: build from identity dict fields directly
            identity = entity.identity or {}
            system_instruction = self._build_system_instruction(
                role=identity.get("role", "AI Assistant"),
                persona=identity.get("persona", ""),
                instructions=identity.get("instructions", ""),
                channel=channel
            )
            voice_config = None
        
        # 3. Load conversation history (last 10 interactions)
        history = await self._load_conversation_history(
            customer_id=customer_id,
            agent_id=agent_id,
            channel=channel,
            limit=10
        )
        
        # 4. Extract LLM config
        llm_config = entity.llm_config or {}
        
        # 5. Extract capabilities
        capabilities = entity.capabilities or {}
        
        # 6. Load tools if configured (future)
        tools = await self._load_agent_tools(entity)
        
        # 7. Fetch API Key — now via centralized ConfigService.resolve_api_key()
        model_name = llm_config.get("model")
        provider = llm_config.get("model_provider", "google")
        api_key = None
        
        try:
            from src.config.service import ConfigService
            config_svc = ConfigService(self.db)
            api_key = await config_svc.resolve_api_key(
                company_id=entity.company_id,
                provider=provider,
                model_name=model_name,
            )
        except Exception as e:
            logger.error(f"Failed to resolve API key for agent {agent_id}: {e}")
        
        if not api_key:
            logger.warning(f"No API key found for agent {agent_id} (provider={provider}, model={model_name})")
        
        # 8. Resolve Live model name for real-time audio
        #    Check llm_config → capabilities → default
        live_model = (
            llm_config.get("live_model")
            or llm_config.get("model")
            or "gemini-3.1-flash-live-preview"
        )
        
        return AgentContext(
            agent_id=agent_id,
            system_instruction=system_instruction,
            conversation_history=history,
            llm_config=llm_config,
            capabilities=capabilities,
            tools=tools,
            api_key=api_key,
            voice_config=voice_config,
            live_model=live_model,
        )
    
    def _build_system_instruction(
        self,
        role: str,
        persona: str,
        instructions: str,
        channel: str
    ) -> str:
        """
        Build system instruction for Gemini from entity identity.
        
        Args:
            role: Agent role (e.g., "EMI Collection Agent")
            persona: Agent persona description
            instructions: Specific instructions
            channel: 'voice' or 'whatsapp'
            
        Returns:
            Formatted system instruction
        """
        instruction = f"""You are {role}.

Persona: {persona}

Instructions:
{instructions}

You are assisting a customer in a real-time {channel} conversation. 
Be concise, helpful, and natural. Listen actively and respond appropriately.
Keep responses brief and conversational - aim for 2-3 sentences maximum.
Avoid repeating yourself or being overly formal."""

        return instruction.strip()
    
    async def _load_conversation_history(
        self,
        customer_id: UUID,
        agent_id: UUID,
        channel: str,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Load recent conversation history for context.
        
        Args:
            customer_id: Customer UUID
            agent_id: Agent UUID
            channel: 'voice' or 'whatsapp'
            limit: Maximum number of turns to load
            
        Returns:
            List of conversation turns in Gemini format
        """
        result = await self.db.execute(
            select(ConversationHistory)
            .where(
                ConversationHistory.customer_id == customer_id,
                ConversationHistory.agent_id == agent_id,
                ConversationHistory.channel == channel
            )
            .order_by(ConversationHistory.timestamp.desc())
            .limit(limit)
        )
        
        turns = result.scalars().all()
        
        # Convert to Gemini format (reverse order - oldest first)
        history = []
        for turn in reversed(turns):
            role = "user" if turn.speaker == "customer" else "model"
            history.append({
                "role": role,
                "parts": [{"text": turn.content}]
            })
        
        logger.info(f"Loaded {len(history)} conversation turns for customer {customer_id}")
        return history
    
    async def _load_agent_tools(self, entity: HierarchicalEntity) -> List:
        """
        Load tools configured for the agent.
        
        Future: Integrate with tool registry.
        For now, returns empty list.
        
        Args:
            entity: HierarchicalEntity object
            
        Returns:
            List of tool definitions
        """
        # TODO: Implement tool loading when Gemini Live API supports function calling
        capabilities = entity.capabilities or {}
        tool_ids = capabilities.get("tools", [])
        
        if tool_ids:
            logger.info(f"Agent has {len(tool_ids)} tools configured (not yet supported in Live API)")
        
        return []

"""RLM ToolSet - Tools for recursive context exploration."""

from __future__ import annotations

from typing import Optional, Dict, Any, List, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import json
import uuid
import re

from iris_llm import ToolSet, tool, Agent, Provider

from .prompts import RLM_SUBAGENT_PROMPT
from .store import SessionStore, IRISStore, InMemoryStore, default_store as _default_store


@dataclass
class RLMSession:
    """Tracks RLM session state."""

    session_id: str
    context: str
    vars: Dict[str, str] = field(default_factory=dict)
    iteration_count: int = 0
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    total_subcalls: int = 0
    completed: bool = False
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    finalized_at: Optional[str] = None
    stage_traces: List[Dict[str, Any]] = field(default_factory=list)


class RLMToolSet(ToolSet):
    """
    RLM-style tools for recursive context exploration.

    The context is stored externally (in IRIS globals when connected),
    and the LLM accesses it through these tools rather than having it
    in the prompt window.
    """

    _session_registry: Dict[str, RLMSession] = {}

    def __init__(
        self,
        context: str,
        provider: Provider,
        model: str = "gpt-4o",
        session_id: Optional[str] = None,
        max_depth: int = 5,
        parent_vars: Optional[Dict[str, str]] = None,
        external_tools: Optional[Dict[str, Callable[..., Any]]] = None,
        sandbox_mode: str = "disabled",
        max_output_chars: int = 4000,
        max_output_tokens: int = 1000,
        execute_timeout_seconds: int = 30,
        semantic_search_fn: Optional[Callable[[str, int, str], List[Dict[str, Any]]]] = None,
        parent_agent: Optional[Agent] = None,
        store: Optional[SessionStore] = None,
    ):
        super().__init__()
        self._store: SessionStore = store if store is not None else _default_store()
        existing = self._session_registry.get(session_id) if session_id else None
        initial_context = existing.context if existing else context
        initial_vars = parent_vars.copy() if parent_vars else (existing.vars.copy() if existing else {})
        self.session = RLMSession(
            session_id=session_id or str(uuid.uuid4()),
            context=initial_context,
            vars=initial_vars,
        )
        if existing:
            self.session.iteration_count = existing.iteration_count
            self.session.total_tokens = existing.total_tokens
            self.session.total_cost_usd = existing.total_cost_usd
            self.session.total_subcalls = existing.total_subcalls
            self.session.created_at = existing.created_at
            self.session.updated_at = existing.updated_at
            self.session.finalized_at = existing.finalized_at
            self.session.completed = existing.completed
            self.session.stage_traces = list(existing.stage_traces)

        self.provider = provider
        self.model = model
        self.max_depth = max_depth
        self.sandbox_mode = sandbox_mode
        self.max_output_chars = max_output_chars
        self.max_output_tokens = max_output_tokens
        self.execute_timeout_seconds = execute_timeout_seconds
        self.external_tools = external_tools or {}
        self.semantic_search_fn = semantic_search_fn
        self.parent_agent = parent_agent
        self.current_depth = 0
        self._finalized = False
        self._final_result: Optional[str] = None

        # Try to persist to IRIS if available
        self._persist_context()
        self._persist_all_vars()
        self._persist_metadata("created", self.session.created_at)
        self._persist_metadata("updated", self.session.updated_at)
        self._session_registry[self.session.session_id] = self.session

    def _persist_context(self):
        self._store.write(self.session.session_id, "context", value=self.session.context)

    def _persist_var(self, name: str, value: str):
        self._store.write(self.session.session_id, "vars", name, value=value)

    def _persist_all_vars(self):
        for key, value in self.session.vars.items():
            self._persist_var(key, value)

    def _persist_metadata(self, key: str, value: str):
        self._store.write(self.session.session_id, "metadata", key, value=value)

    def _estimate_tokens(self, text: str) -> int:
        return max(1, len(text) // 4)

    def _create_agent(self):
        """Create an agent, using create_child_agent when a parent is available.

        create_child_agent shares the parent's tokio runtime, avoiding the
        nested block_on() panic that occurs when Agent.run() is called from
        within a tool callback.
        """
        if self.parent_agent is not None:
            return self.parent_agent.create_child_agent(self.model, self.provider)
        try:
            return Agent.with_provider(self.model, self.provider)
        except TypeError:
            return Agent.with_provider(self.provider)

    def _record_tool_call(self, output: str = ""):
        self.session.iteration_count += 1
        self.session.total_tokens += self._estimate_tokens(output)
        self.session.updated_at = datetime.now(timezone.utc).isoformat()
        self._persist_metadata("iterations", str(self.session.iteration_count))
        self._persist_metadata("tokens", str(self.session.total_tokens))
        self._persist_metadata("cost_usd", f"{self.session.total_cost_usd:.6f}")
        self._persist_metadata("updated", self.session.updated_at)
        self._session_registry[self.session.session_id] = self.session

    @property
    def is_finalized(self) -> bool:
        return self._finalized

    @property
    def final_result(self) -> Optional[str]:
        return self._final_result

    # ==================== Context Tools ====================

    @tool
    def context_info(self) -> str:
        """Get metadata about the context.

        Returns:
            Context length in characters and estimated tokens.
        """
        length = len(self.session.context)
        tokens = length // 4  # Rough estimate
        lines = self.session.context.count("\n")
        output = (
            f"Length: {length:,} chars, ~{tokens:,} tokens, {lines:,} lines, "
            f"session={self.session.session_id}, vars={len(self.session.vars)}"
        )
        self._record_tool_call(output)
        return output

    @tool
    def peek_context(self, start: int = 0, length: int = 1000) -> str:
        """View a slice of the context without loading it all.

        Args:
            start: Starting character position (0-indexed)
            length: Number of characters to return (max 5000)

        Returns:
            The requested slice of context
        """
        length = min(length, 5000)  # Cap at 5000 chars
        end = start + length
        total = len(self.session.context)

        if start >= total:
            output = f"ERROR: start ({start}) is beyond context length ({total})"
            self._record_tool_call(output)
            return output

        slice_text = self.session.context[start:end]
        output = f"[chars {start}-{min(end, total)} of {total}]\n{slice_text}"
        self._record_tool_call(output)
        return output

    @tool
    def filter_context(self, pattern: str) -> str:
        """Filter context sections matching a regex pattern.

        Args:
            pattern: Regular expression pattern (case-insensitive)

        Returns:
            All matching sections, separated by ---
        """
        try:
            matches = re.findall(pattern, self.session.context, re.MULTILINE | re.IGNORECASE)
        except re.error as e:
            output = f"ERROR: Invalid regex pattern: {e}"
            self._record_tool_call(output)
            return output

        if not matches:
            output = "No matches found"
            self._record_tool_call(output)
            return output

        # Limit results
        if len(matches) > 20:
            result = "\n---\n".join(matches[:20])
            output = f"{result}\n\n... and {len(matches) - 20} more matches"
            self._record_tool_call(output)
            return output

        output = "\n---\n".join(matches)
        self._record_tool_call(output)
        return output

    @tool
    def search_context(self, query: str, top_k: int = 5) -> str:
        """Semantic search within the context.

        Args:
            query: Search query
            top_k: Number of results to return (max 10)

        Returns:
            Matching excerpts with relevance scores
        """
        top_k = min(top_k, 10)

        if self.semantic_search_fn is not None:
            try:
                semantic_results = self.semantic_search_fn(query, top_k, self.session.context)
                if semantic_results:
                    rendered = ["[mode=semantic-adapter]"]
                    for idx, row in enumerate(semantic_results[:top_k]):
                        excerpt = str(row.get("excerpt", ""))[:500]
                        score = row.get("score", "n/a")
                        rendered.append(f"[Chunk {idx}, score={score}]\n{excerpt}...")
                    output = "\n\n".join(rendered)
                    self._record_tool_call(output)
                    return output
            except Exception as exc:
                output = f"[mode=semantic-adapter-error] {exc}"
                self._record_tool_call(output)
                return output

        mode = "keyword-fallback"
        # Try to use iris-vector-rag if available
        try:
            from iris_vector_rag.storage import IRISVectorStore  # noqa: F401
            mode = "semantic-intended-keyword-fallback"
        except ImportError:
            pass

        # Fallback: simple keyword search
        query_lower = query.lower()
        chunks = self._chunk_context(1000)

        scored = []
        for i, chunk in enumerate(chunks):
            # Simple scoring: count query word occurrences
            score = sum(1 for word in query_lower.split() if word in chunk.lower())
            if score > 0:
                scored.append((score, i, chunk))

        scored.sort(reverse=True)
        results = scored[:top_k]

        if not results:
            output = f"[mode={mode}] No relevant sections found"
            self._record_tool_call(output)
            return output

        output = []
        for score, idx, chunk in results:
            output.append(f"[Chunk {idx}, score={score}]\n{chunk[:500]}...")
        rendered = f"[mode={mode}]\n" + "\n\n".join(output)
        self._record_tool_call(rendered)
        return rendered

    @tool
    def chunk_context(self, chunk_size: int = 1000) -> str:
        """Split context into chunks and return chunk metadata.

        Args:
            chunk_size: Chunk size in characters

        Returns:
            Chunk count and range metadata
        """
        chunk_size = max(1, chunk_size)
        chunks = self._chunk_context(chunk_size)
        lines = []
        total = len(self.session.context)
        for i in range(len(chunks)):
            start = i * chunk_size
            end = min(start + chunk_size, total)
            lines.append(f"chunk[{i}]={start}:{end}")
        output = f"total_chunks={len(chunks)}, chunk_size={chunk_size}\n" + "\n".join(lines[:200])
        self._record_tool_call(output)
        return output

    def _chunk_context(self, chunk_size: int) -> List[str]:
        """Split context into chunks."""
        context = self.session.context
        chunks = []
        for i in range(0, len(context), chunk_size):
            chunks.append(context[i : i + chunk_size])
        return chunks

    # ==================== State Tools ====================

    @tool
    def store_var(self, name: str, value: str) -> str:
        """Store a value in session state for later use.

        Args:
            name: Variable name (use descriptive names)
            value: Value to store

        Returns:
            Confirmation message
        """
        self.session.vars[name] = value
        self._persist_var(name, value)
        preview = value[:100] + "..." if len(value) > 100 else value
        output = f"Stored '{name}' = {preview}"
        self._record_tool_call(output)
        return output

    @tool
    def get_var(self, name: str) -> str:
        """Retrieve a stored variable.

        Args:
            name: Variable name

        Returns:
            The stored value, or error if not found
        """
        if name not in self.session.vars:
            available = list(self.session.vars.keys())
            output = f"ERROR: Variable '{name}' not found. Available: {available}"
            self._record_tool_call(output)
            return output
        output = self.session.vars[name]
        self._record_tool_call(output)
        return output

    @tool
    def list_vars(self) -> str:
        """List all stored variables.

        Returns:
            Names and previews of all stored variables
        """
        if not self.session.vars:
            output = "No variables stored yet"
            self._record_tool_call(output)
            return output

        lines = []
        for name, value in self.session.vars.items():
            preview = value[:80] + "..." if len(value) > 80 else value
            preview = preview.replace("\n", " ")
            lines.append(f"- {name}: {preview}")

        output = "\n".join(lines)
        self._record_tool_call(output)
        return output

    # ==================== Large Output Handling Tools ====================

    @tool
    def peek_var(self, name: str, start: int = 0, length: int = 500) -> str:
        """View a slice of a stored variable without loading it all.

        Use this to explore large tool outputs (JIRA results, SQL data, etc.)
        that were auto-stored due to size.

        Args:
            name: Variable name
            start: Start position (0-based)
            length: Number of characters to return (max 2000)

        Returns:
            The requested slice of the variable
        """
        if name not in self.session.vars:
            available = list(self.session.vars.keys())
            output = f"ERROR: Variable '{name}' not found. Available: {available}"
            self._record_tool_call(output)
            return output

        value = self.session.vars[name]
        length = min(length, 2000)
        end = start + length

        slice_text = value[start:end]
        total_len = len(value)

        if end < total_len:
            output = (
                f"{slice_text}\n\n[Showing {start}-{end} of {total_len} chars. "
                f"Use peek_var('{name}', {end}, {length}) for more]"
            )
            self._record_tool_call(output)
            return output
        self._record_tool_call(slice_text)
        return slice_text

    @tool
    def search_var(self, name: str, query: str, top_k: int = 5) -> str:
        """Search within a stored variable.

        Use this to find relevant sections in large tool outputs.

        Args:
            name: Variable name to search in
            query: Search query
            top_k: Number of results

        Returns:
            Matching excerpts from the variable
        """
        if name not in self.session.vars:
            available = list(self.session.vars.keys())
            output = f"ERROR: Variable '{name}' not found. Available: {available}"
            self._record_tool_call(output)
            return output

        value = self.session.vars[name]
        top_k = min(top_k, 10)

        # Split into chunks and search
        chunk_size = 500
        chunks = [value[i : i + chunk_size] for i in range(0, len(value), chunk_size)]

        query_lower = query.lower()
        scored = []
        for i, chunk in enumerate(chunks):
            score = sum(1 for word in query_lower.split() if word in chunk.lower())
            if score > 0:
                scored.append((score, i * chunk_size, chunk))

        scored.sort(reverse=True)
        results = scored[:top_k]

        if not results:
            output = f"No matches for '{query}' in '{name}'"
            self._record_tool_call(output)
            return output

        output = []
        for score, pos, chunk in results:
            output.append(f"[Position {pos}, score={score}]\n{chunk[:400]}...")

        rendered = "\n\n".join(output)
        self._record_tool_call(rendered)
        return rendered

    @tool
    def summarize_var(self, name: str, focus: str = "") -> str:
        """Get an RLM-generated summary of a large variable.

        Spawns a sub-agent to summarize the content.

        Args:
            name: Variable name to summarize
            focus: Optional focus area (e.g., "bugs", "high priority")

        Returns:
            A concise summary of the variable contents
        """
        if name not in self.session.vars:
            available = list(self.session.vars.keys())
            output = f"ERROR: Variable '{name}' not found. Available: {available}"
            self._record_tool_call(output)
            return output

        value = self.session.vars[name]

        focus_text = f" Focus on: {focus}" if focus else ""
        task = f"Summarize this data concisely, preserving key details.{focus_text}"

        # Use spawn_subagent to summarize
        output = self._spawn_subagent_internal(task, value)
        self._record_tool_call(output)
        return output

    def _setup_and_run_subagent(
        self,
        task: str,
        toolset: "RLMToolSet",
        system_prompt: str,
        model: Optional[str] = None,
    ) -> str:
        """Create and run a sub-agent using create_child_agent.

        When parent_agent is set, create_child_agent shares the parent's
        tokio runtime so nested Agent.run() calls work without panicking.
        """
        sub_agent = self._create_agent()
        if model and hasattr(sub_agent, "set_model"):
            sub_agent.set_model(model)
        sub_agent.add_tool_set(toolset)
        sub_agent.set_system_prompt(system_prompt)
        return sub_agent.run(task)

    def _spawn_subagent_internal(self, task: str, context: str) -> str:
        """Internal method for spawning sub-agents (used by tools)."""
        if self.current_depth >= self.max_depth:
            # Fallback: return truncated content
            return f"[Max depth reached. First 1000 chars:]\n{context[:1000]}..."

        sub_toolset = RLMToolSet(
            context=context,
            provider=self.provider,
            model=self.model,
            session_id=self.session.session_id,
            max_depth=self.max_depth,
            parent_vars=self.session.vars,
            parent_agent=self.parent_agent,
        )
        sub_toolset.current_depth = self.current_depth + 1

        try:
            result = self._setup_and_run_subagent(
                task=task,
                toolset=sub_toolset,
                system_prompt=RLM_SUBAGENT_PROMPT,
            )
        except Exception as exc:
            return f"[Subagent error: {exc}]"
        self.session.total_subcalls += 1
        self.session.total_tokens += self._estimate_tokens(result)
        self._persist_metadata("subcalls", str(self.session.total_subcalls))
        self._persist_metadata("tokens", str(self.session.total_tokens))
        return result

    def call_tool_with_rlm(
        self,
        tool_name: str,
        tool_func: Callable[..., Any],
        args: dict,
        max_output_chars: Optional[int] = None,
        max_output_tokens: Optional[int] = None,
    ) -> str:
        """Call any tool and auto-handle large outputs.

        If the tool returns > max_output_chars, the output is stored
        and a reference is returned instead.

        Args:
            tool_name: Name for storing the result
            tool_func: The tool function to call
            args: Arguments to pass to the tool
            max_output_chars: Threshold for auto-storing in chars
            max_output_tokens: Threshold for auto-storing in tokens

        Returns:
            Either the direct result, or a reference to stored data
        """
        char_limit = max_output_chars if max_output_chars is not None else self.max_output_chars
        token_limit = max_output_tokens if max_output_tokens is not None else self.max_output_tokens
        result = tool_func(**args)
        result_str = str(result)
        estimated_tokens = self._estimate_tokens(result_str)

        if len(result_str) <= char_limit and estimated_tokens <= token_limit:
            self._record_tool_call(result_str)
            return result_str

        # Store and return reference
        var_name = f"{tool_name}_result"
        self.session.vars[var_name] = result_str
        self._persist_var(var_name, result_str)

        # Return summary reference
        preview = result_str[:200].replace("\n", " ")
        return (
            f"Large output ({len(result_str)} chars, ~{estimated_tokens} tokens) stored in '{var_name}'.\n"
            f"Preview: {preview}...\n\n"
            f"Use these tools to explore:\n"
            f"- peek_var('{var_name}', 0, 500) - View a section\n"
            f"- search_var('{var_name}', 'keyword') - Search within\n"
            f"- summarize_var('{var_name}') - Get summary"
        )
        self._record_tool_call(output)
        return output

    @tool
    def rlm_call_tool(self, tool_name: str, args: Dict[str, Any]) -> str:
        """Call a registered external tool with large-output interception."""
        if tool_name not in self.external_tools:
            return (
                f"ERROR: Tool '{tool_name}' not registered. "
                "Provide external_tools mapping when constructing RLMToolSet."
            )
        return self.call_tool_with_rlm(
            tool_name=tool_name,
            tool_func=self.external_tools[tool_name],
            args=args,
            max_output_chars=self.max_output_chars,
            max_output_tokens=self.max_output_tokens,
        )

    # ==================== Sub-Agent Tools ====================

    @tool
    def spawn_subagent(self, task: str, context_slice: str = "") -> str:
        """Spawn a sub-agent to handle a subtask.

        Use this for complex subtasks that need focused attention.
        The sub-agent has the same tools but a fresh prompt.

        Args:
            task: The task for the sub-agent to complete
            context_slice: Optional context to provide (defaults to full context)

        Returns:
            The sub-agent's result
        """
        if self.current_depth >= self.max_depth:
            output = f"ERROR: Max recursion depth ({self.max_depth}) reached. Cannot spawn sub-agent."
            self._record_tool_call(output)
            return output

        # Use provided slice or full context
        sub_context = context_slice if context_slice else self.session.context

        # Create sub-agent toolset with incremented depth
        sub_toolset = RLMToolSet(
            context=sub_context,
            provider=self.provider,
            model=self.model,
            session_id=self.session.session_id,  # Share session
            max_depth=self.max_depth,
            parent_vars=self.session.vars,  # Share vars
            parent_agent=self.parent_agent,
        )
        sub_toolset.current_depth = self.current_depth + 1

        try:
            result = self._setup_and_run_subagent(
                task=task,
                toolset=sub_toolset,
                system_prompt=RLM_SUBAGENT_PROMPT,
                model=self.model,
            )
        except Exception as exc:
            output = f"ERROR: Subagent failed: {exc}"
            self._record_tool_call(output)
            return output

        # Merge any new vars from sub-agent
        for key, value in sub_toolset.session.vars.items():
            self.session.vars[key] = value
            self._persist_var(key, value)

        self.session.total_subcalls += 1
        self.session.total_tokens += self._estimate_tokens(result)
        self._persist_metadata("subcalls", str(self.session.total_subcalls))
        self._persist_metadata("tokens", str(self.session.total_tokens))
        self._record_tool_call(result)
        return result

    # ==================== Termination ====================

    def _resolve_result_refs(self, result: str) -> str:
        """Resolve simple variable references in finalize text."""
        def _replace(match: re.Match[str]) -> str:
            var_name = match.group(1).strip()
            return self.session.vars.get(var_name, f"<missing:{var_name}>")

        return re.sub(r"\{\{var:([a-zA-Z0-9_\-]+)\}\}", _replace, result)

    @tool
    def execute_python(self, code: str) -> str:
        """Execute constrained Python code.

        MVP default is disabled for safety.
        """
        if self.sandbox_mode != "restricted":
            output = (
                "ERROR: execute_python is disabled in MVP mode. "
                "Enable sandbox_mode=restricted to use this tool."
            )
            self._record_tool_call(output)
            return output

        if "import " in code and "import iris" not in code:
            output = "ERROR: Only `import iris` is allowed in restricted mode."
            self._record_tool_call(output)
            return output

        safe_builtins = {
            "len": len,
            "sum": sum,
            "min": min,
            "max": max,
            "sorted": sorted,
            "str": str,
            "int": int,
            "float": float,
            "bool": bool,
            "list": list,
            "dict": dict,
            "set": set,
            "tuple": tuple,
            "range": range,
            "enumerate": enumerate,
        }
        local_vars: Dict[str, Any] = {"vars": self.session.vars.copy()}
        try:
            import iris  # type: ignore
            local_vars["iris"] = iris
        except Exception:
            pass

        def _run() -> Dict[str, Any]:
            exec_globals = {"__builtins__": safe_builtins}
            exec(code, exec_globals, local_vars)
            return local_vars

        try:
            from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(_run)
                final_locals = future.result(timeout=self.execute_timeout_seconds)
        except FuturesTimeoutError:
            output = f"ERROR: execute_python timed out after {self.execute_timeout_seconds}s"
            self._record_tool_call(output)
            return output
        except Exception as exc:
            output = f"ERROR: execute_python failed: {exc}"
            self._record_tool_call(output)
            return output

        session_vars = final_locals.get("vars")
        if isinstance(session_vars, dict):
            self.session.vars = {k: str(v) for k, v in session_vars.items()}
            self._persist_all_vars()
        output = "execute_python completed in restricted mode"
        self._record_tool_call(output)
        return output

    @tool
    def finalize(self, result: str) -> str:
        """Signal completion and return the final result.

        Call this exactly once when you have the complete answer.
        This ends the RLM loop.

        Args:
            result: The final answer

        Returns:
            Confirmation with the result
        """
        resolved = self._resolve_result_refs(result)
        self._finalized = True
        self._final_result = resolved
        self.session.completed = True
        self.session.finalized_at = datetime.now(timezone.utc).isoformat()
        self.session.updated_at = self.session.finalized_at

        sid = self.session.session_id
        self._store.write(sid, "metadata", "completed", value="true")
        self._store.write(sid, "metadata", "iterations", value=str(self.session.iteration_count))
        self._store.write(sid, "metadata", "tokens", value=str(self.session.total_tokens))
        self._store.write(sid, "metadata", "cost_usd", value=f"{self.session.total_cost_usd:.6f}")
        self._store.write(sid, "metadata", "finalized", value=self.session.finalized_at)
        self._store.write(sid, "result", value=resolved)

        stats = (
            f"iterations={self.session.iteration_count}, "
            f"tokens~{self.session.total_tokens}, "
            f"subcalls={self.session.total_subcalls}"
        )
        output = f"FINAL: {resolved}\n[{stats}]"
        self._record_tool_call(output)
        return output

    @classmethod
    def load_session_snapshot(
        cls, session_id: str, store: Optional[SessionStore] = None
    ) -> Optional[Dict[str, Any]]:
        """Load a session snapshot from in-memory registry or a SessionStore."""
        if session_id in cls._session_registry:
            session = cls._session_registry[session_id]
            return {
                "context": session.context,
                "vars": session.vars.copy(),
                "iterations": session.iteration_count,
                "tokens": session.total_tokens,
                "cost_usd": session.total_cost_usd,
            }

        s = store if store is not None else _default_store()
        context = s.read(session_id, "context")
        if not context:
            return None
        vars_json = s.read(session_id, "metadata", "vars_json") or "{}"
        try:
            vars_dict = json.loads(vars_json)
            if not isinstance(vars_dict, dict):
                vars_dict = {}
        except Exception:
            vars_dict = {}
        return {"context": context, "vars": {str(k): str(v) for k, v in vars_dict.items()}}

    @classmethod
    def cleanup_expired_sessions(
        cls,
        ttl_seconds: int = 86400,
        now: Optional[datetime] = None,
        store: Optional[SessionStore] = None,
    ) -> int:
        """Remove expired in-memory sessions and mark store metadata."""
        now = now or datetime.now(timezone.utc)
        s = store if store is not None else _default_store()
        to_delete: List[str] = []
        for session_id, session in cls._session_registry.items():
            updated = datetime.fromisoformat(session.updated_at)
            if now - updated > timedelta(seconds=ttl_seconds):
                to_delete.append(session_id)
        for session_id in to_delete:
            del cls._session_registry[session_id]
            s.write(session_id, "metadata", "expired", value="true")
        return len(to_delete)



# ==================== DSPy Refactor Extensions ====================

def _rlm_persist_stage_trace(self: RLMToolSet, event: Dict[str, Any]) -> None:
    idx = len(getattr(self.session, "stage_traces", []))
    self._store.write(self.session.session_id, "traces", str(idx), value=json.dumps(event))


def _rlm_emit_stage_trace(
    self: RLMToolSet,
    stage: str,
    outcome: str,
    detail: str = "",
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    if not hasattr(self.session, "stage_traces"):
        self.session.stage_traces = []
    event = {
        "stage": stage,
        "outcome": outcome,
        "detail": detail,
        "metadata": metadata or {},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    self.session.stage_traces.append(event)
    _rlm_persist_stage_trace(self, event)
    return event


def _rlm_classify_payload_size(self: RLMToolSet, payload: str) -> str:
    size = len(payload)
    if size < 1000:
        return "small"
    if size < 10000:
        return "medium"
    return "large"


def _rlm_looks_healthcare_payload(self: RLMToolSet, payload: str) -> bool:
    lowered = payload.lower()
    return any(token in lowered for token in ["patient", "encounter", "medication", "claim", "fhir"])


def _rlm_deidentify_healthcare_payload(self: RLMToolSet, payload: str) -> str:
    if "FAIL_DEID" in payload:
        raise ValueError("de-identification failed for payload")
    payload = re.sub(r"(?i)patient\s+name\s*[:=]\s*[^,\n]+", "Patient Name=[REDACTED]", payload)
    payload = re.sub(r"(?i)\b(name|mrn|ssn|dob)\s*[:=]\s*[^,\n]+", r"\1=[REDACTED]", payload)
    return payload


def _rlm_prepare_payload_for_reasoning(
    self: RLMToolSet,
    payload: str,
    is_healthcare: Optional[bool] = None,
) -> str:
    healthcare = _rlm_looks_healthcare_payload(self, payload) if is_healthcare is None else is_healthcare
    if not healthcare:
        return payload
    try:
        return _rlm_deidentify_healthcare_payload(self, payload)
    except Exception as exc:
        remediation = (
            "FAIL_CLOSED: Healthcare payload preprocessing failed. "
            "Remediation: verify de-identification rules and re-run with minimum necessary fields. "
            f"Details: {exc}"
        )
        self.session.vars["remediation_guidance"] = remediation
        try:
            self._persist_var("remediation_guidance", remediation)
        except Exception:
            pass
        _rlm_emit_stage_trace(self, "payload_filter", "terminal_error", remediation)
        return remediation


# Bind module-level helpers as instance methods using explicit descriptors rather
# than post-hoc attribute assignment. This preserves subclassing and IDE navigation.
RLMToolSet.emit_stage_trace = _rlm_emit_stage_trace  # type: ignore[method-assign]
RLMToolSet.classify_payload_size = _rlm_classify_payload_size  # type: ignore[method-assign]
RLMToolSet.deidentify_healthcare_payload = _rlm_deidentify_healthcare_payload  # type: ignore[method-assign]
RLMToolSet.prepare_payload_for_reasoning = _rlm_prepare_payload_for_reasoning  # type: ignore[method-assign]

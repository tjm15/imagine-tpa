import sys
import os
import yaml
import json
import asyncio
import argparse
from pathlib import Path
from jsonschema import validate, ValidationError
from unittest.mock import patch
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012
from jsonschema.validators import validator_for

# Add project root to path
sys.path.append(os.getcwd())
sys.path.append(os.path.join(os.getcwd(), 'apps', 'api'))

from tpa_api.grammar.orchestrator import GrammarOrchestrator, MoveType

def load_yaml(path):
    with open(path, 'r') as f:
        return yaml.safe_load(f)

def load_json(path):
    with open(path, 'r') as f:
        return json.load(f)

class Runner:
    def __init__(self, spec_path, mode='mock'):
        self.spec = load_yaml(spec_path)
        self.mode = mode
        self.move_name = self.spec['move']
        self.fixtures_dir = Path("agents/mdk/fixtures")
        self.schemas_dir = Path("schemas")

    async def run(self):
        print(f"[Runner] Starting for move: {self.move_name} [Mode: {self.mode.upper()}]")
        
        # 1. Load Fixture
        fixture_file = self.spec.get('fixture')
        if not fixture_file:
             print("[Error] Spec missing 'fixture' field.")
             return

        fixture_path = self.fixtures_dir / fixture_file
        if not fixture_path.exists():
            print(f"[Error] Fixture not found: {fixture_path}")
            return
        
        context = load_json(fixture_path)
        print(f"[Info] Loaded context from {fixture_path}")

        # 2. Prepare Environment
        if self.mode == 'mock':
             await self._run_mock(context)
        else:
             await self._run_live(context)

    async def _run_mock(self, context):
        mock_response = self.spec.get('mock_llm_response')
        response_str = json.dumps(mock_response) if isinstance(mock_response, (dict, list)) else str(mock_response)
        
        print("[Mock] Mocking `_generate_completion_sync`...")
        with patch('tpa_api.grammar.orchestrator._generate_completion_sync') as mock_llm:
            mock_llm.return_value = response_str
            await self._execute(context)
            
            # Verify Mock Interaction
            if mock_llm.called:
                args = mock_llm.call_args
                prompt = args.kwargs.get('prompt') or (args.args[0] if args.args else "")
                print(f"\n[Info] Captured Prompt (Mock):\n{prompt[:200]}...")

    async def _run_live(self, context):
        print("[Live] Connecting to REAL services (expecting TPA_LLM_BASE_URL etc to be set)...")
        try:
            await self._execute(context)
        except Exception as e:
            print(f"[Error] Live Execution Failed: {e}")
            print("[Tip] Check if 'tpa-llm' or equivalent is running and accessible.")

    async def _execute(self, context):
        orch = GrammarOrchestrator(
            run_id=context.get('run_id', 'test-run'),
            political_framing=context.get('political_framing', 'neutral')
        )
        
        try:
            move_enum = MoveType(self.move_name)
        except ValueError:
            print(f"[Error] Invalid move name: {self.move_name}. Valid options: {[m.value for m in MoveType]}")
            return

        print(f"[Exec] Executing {move_enum.value}...")
        event = await orch.execute_move(move_enum, context.get('input_context', {}))
        
        print("\n--- Move Output ---")
        print(json.dumps(event.output_artifacts, indent=2))
        
        self._validate(event.output_artifacts)

    def _validate(self, artifacts):
        print("\n--- Validation ---")
        expected_schemas = self.spec.get('validation', {}).get('schemas', {})
        
        # Pre-load registry
        registry = Registry()
        for schema_file in self.schemas_dir.glob("*.schema.json"):
             try:
                 with open(schema_file) as f:
                     s = json.load(f)
                     resource = Resource.from_contents(s)
                     registry = registry.with_resource(uri=schema_file.name, resource=resource)
             except Exception:
                 pass # Skip broken schemas

        for key, schema_file in expected_schemas.items():
            schema_path = self.schemas_dir / schema_file
            if not schema_path.exists():
                print(f"[Warn] Schema file missing: {schema_path}")
                continue
                
            with open(schema_path) as f:
                schema_data = json.load(f)

            data = artifacts.get(key)
            if data is None:
                print(f"[Error] Missing artifact key: {key}")
                continue
            
            # Use validator with registry
            Validator = validator_for(schema_data)
            validator = Validator(schema_data, registry=registry)

            try:
                if isinstance(data, list):
                    for item in data:
                        validator.validate(item)
                else:
                    validator.validate(data)
                print(f"[Pass] {key}: Schema Valid ({schema_file})")
            except ValidationError as e:
                print(f"[Fail] {key}: Schema Invalid - {e.message}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("spec", help="Path to YAML spec file")
    parser.add_argument("--mode", choices=['mock', 'live'], default='mock', help="Execution mode")
    args = parser.parse_args()
    
    runner = Runner(args.spec, mode=args.mode)
    asyncio.run(runner.run())

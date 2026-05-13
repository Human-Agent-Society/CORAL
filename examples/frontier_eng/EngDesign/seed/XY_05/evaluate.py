import json
import re

def evaluate_llm_response(llm_response):
    # llm_response = Response_structure(**json.loads(llm_response))
    if isinstance(llm_response, str):
        try:
            llm_response = Response_structure(**json.loads(llm_response))
        except json.JSONDecodeError:
            # If direct JSON parsing fails, try to find JSON-like content
            print("Failed to parse response")
            try:
                json_match = re.search(r'\{.*\}', llm_response, re.DOTALL)
                if json_match:
                    json_str = json_match.group(0)
                    llm_response = Response_structure(**json.loads(json_str))
                else:
                    return False, {"error": "fail extracting JSON from response"}, 0, 0
            except Exception as e:
                print(f"Error parsing response: {e}")
                return False, {"error": str(e)}, 0, 0
            

    score = 0  # Reasoning removed, redistribute its 20 points to other categories
    details = {}
    correct_ports = {
        'ADD': {'ld_reg': '1', 'ld_ir': '0', 'ld_pc': '0', 'ld_cc': '1', 'gateALU': '1', 'gateMDR': '0', 'mem_en': '0', 'mem_we': '0'},
        'AND': {'ld_reg': '1', 'ld_ir': '0', 'ld_pc': '0', 'ld_cc': '1', 'gateALU': '1', 'gateMDR': '0', 'mem_en': '0', 'mem_we': '0'},
        'NOT': {'ld_reg': '1', 'ld_ir': '0', 'ld_pc': '0', 'ld_cc': '1', 'gateALU': '1', 'gateMDR': '0', 'mem_en': '0', 'mem_we': '0'},
        'LDR': {'ld_reg': '1', 'ld_ir': '0', 'ld_pc': '0', 'ld_cc': '1', 'gateALU': '0', 'gateMDR': '1', 'mem_en': '1', 'mem_we': '0'}, 
        'STR': {'ld_reg': '0', 'ld_ir': '0', 'ld_pc': '0', 'ld_cc': '0', 'gateALU': '0', 'gateMDR': '0', 'mem_en': '1', 'mem_we': '1'}, 
        'BR':  {'ld_reg': '0', 'ld_ir': '0', 'ld_pc': '1', 'ld_cc': '0', 'gateALU': '0', 'gateMDR': '0', 'mem_en': '0', 'mem_we': '0'}, 
        'JMP': {'ld_reg': '0', 'ld_ir': '0', 'ld_pc': '1', 'ld_cc': '0', 'gateALU': '0', 'gateMDR': '0', 'mem_en': '0', 'mem_we': '0'}, 
        'JSR': {'ld_reg': '1', 'ld_ir': '0', 'ld_pc': '1', 'ld_cc': '0', 'gateALU': '0', 'gateMDR': '0', 'mem_en': '0', 'mem_we': '0'}, 
        'SWAP': {'ld_reg': '1', 'ld_ir': '0', 'ld_pc': '0', 'ld_cc': '1', 'gateALU': '1', 'gateMDR': '0', 'mem_en': '0', 'mem_we': '0'} 
    }
    
    #these are additional operation i add to increase difficulty
    alternative_ports = {
        'STR': {'ld_reg': '0', 'ld_ir': '0', 'ld_pc': '0', 'ld_cc': 'X', 'gateALU': 'X', 'gateMDR': 'X', 'mem_en': '1', 'mem_we': '1'}, 
        'STR': {'ld_reg': '0', 'ld_ir': '0', 'ld_pc': '0', 'ld_cc': '0', 'gateALU': '1', 'gateMDR': '0', 'mem_en': '1', 'mem_we': '1'}, 
        'BR': {'ld_reg': '0', 'ld_ir': '0', 'ld_pc': '1', 'ld_cc': 'X', 'gateALU': 'X', 'gateMDR': 'X', 'mem_en': '0', 'mem_we': '0'},
        'JMP': {'ld_reg': '0', 'ld_ir': '0', 'ld_pc': '1', 'ld_cc': 'X', 'gateALU': 'X', 'gateMDR': 'X', 'mem_en': '0', 'mem_we': '0'}, 
        'JSR': {'ld_reg': '1', 'ld_ir': '0', 'ld_pc': '1', 'ld_cc': 'X', 'gateALU': 'X', 'gateMDR': 'X', 'mem_en': '0', 'mem_we': '0'}, 
        'LDR': {'ld_reg': '1', 'ld_ir': '0', 'ld_pc': '0', 'ld_cc': '0', 'gateALU': '0', 'gateMDR': '1', 'mem_en': '1', 'mem_we': '0'}, 
        'JSR': {'ld_reg': '1', 'ld_ir': '0', 'ld_pc': '1', 'ld_cc': '0', 'gateALU': '1', 'gateMDR': '0', 'mem_en': '0', 'mem_we': '0'}
    }

    # Correct state transitions for each instruction
    correct_states = {
        'ADD': {'current': 's_1', 'next': 's_18'},
        'AND': {'current': 's_5', 'next': 's_18'},
        'NOT': {'current': 's_9', 'next': 's_18'},
        'LDR': {'current': 's_6', 'next': 's_25_1', 'sequence': 's_25_1,s_25_2,s_25_3,s_27,s_18'},
        'STR': {'current': 's_7', 'next': 's_23', 'sequence': 's_23,s_16_1,s_16_2,s_16_3,s_18'},
        'BR': {'current': 's_0', 'next_taken': 's_22', 'next_not_taken': 's_18', 'sequence_taken': 's_22,s_18'},
        'JMP': {'current': 's_12', 'next': 's_18'},
        'JSR': {'current': 's_4', 'next': 's_21', 'sequence': 's_21,s_18'},
        'SWAP': {'current': None, 'next': None}
    }

    # Normalize port values in user response to ensure everything is a string
    if hasattr(llm_response.config, 'ports_table') and llm_response.config.ports_table:#converting any integer values to their string representations (e.g. '0', '1')
        for instr, ports in llm_response.config.ports_table.items():
            for port, value in ports.items():
                if isinstance(value, int):
                    ports[port] = str(value)

    critical_errors = False
    error_messages = []
    
    # Check for bus conflicts
    for instr, ports in llm_response.config.ports_table.items():
        bus_drivers = 0
        if str(ports.get('gateALU', '0')) == '1':
            bus_drivers += 1
        if str(ports.get('gateMDR', '0')) == '1':
            bus_drivers += 1
        
        if bus_drivers > 1:
            critical_errors = True
            error_messages.append(f"Bus conflict in {instr}: multiple devices driving bus simultaneously")
    
    # Check for invalid memory operations
    for instr, ports in llm_response.config.ports_table.items():
        # Memory write enabled but memory not enabled
        if str(ports.get('mem_we', '0')) == '1' and str(ports.get('mem_en', '0')) == '0':
            critical_errors = True
            error_messages.append(f"Invalid memory operation in {instr}: write enabled but memory not enabled")

    # Calculate port assignment score - capped at 50 points
    max_ports_score = 60  # Reduced from 54
    ports_score = 0  # Reasoning removed, redistribute its 20 points to other categories
    for instr, ports in correct_ports.items():
        user_ports = llm_response.config.ports_table.get(instr, {})
        instr_score = 0  # Reasoning removed, redistribute its 20 points to other categories
        total_ports = len(ports)
        
        # Check each port value against the correct values
        for port, correct_val in ports.items():
            if port in user_ports:
                user_val = str(user_ports[port]) 
                
                # PC handling - if PC is set to 1 for non-branch/jump instructions
                if port == 'ld_pc' and instr not in ['BR', 'JMP', 'JSR'] and user_val == '1':
                    continue
                if user_val == correct_val:
                    instr_score += 1
                elif instr in alternative_ports and port in alternative_ports[instr] and user_val == alternative_ports[instr][port]:
                    instr_score += 0.75
                elif instr in alternative_ports and port in alternative_ports[instr] and alternative_ports[instr][port] == 'X' and user_val in ['0', '1']:
                    instr_score += 0.5
        
        # Calculate score as a percentage of correct ports for this instruction 
        instr_percentage = instr_score / total_ports
        ports_score += instr_percentage * (max_ports_score / 9)  # Scale by number of instructions
    
    # Add ports score to total (max 50 points)
    score += min(max_ports_score, ports_score)
    details['ports_assignment'] = f'{int(min(max_ports_score, ports_score))}/{max_ports_score}'

    # Enhanced reasoning evaluation (max 20 points)
    # max_reasoning_score = 20
    # reasoning_score = 0  # Reasoning removed, redistribute its 20 points to other categories
    # if hasattr(llm_response.config, 'explanation') and llm_response.config.explanation:
    #     for instr in correct_ports.keys():
    #         if instr in llm_response.config.explanation:
    #             explanation = llm_response.config.explanation[instr]
    #             instr_reasoning_score = 0  # Reasoning removed, redistribute its 20 points to other categories
                
    #             # Basic length check
    #             if len(explanation) > 10:
    #                 instr_reasoning_score += 1
                
    #             # Technical precision
    #             tech_terms = ['ALU', 'register', 'memory', 'bus', 'PC', 'IR', 'CC']
    #             term_count = sum(1 for term in tech_terms if re.search(rf'\b{term}\b', explanation, re.IGNORECASE))
    #             if term_count >= 2:
    #                 instr_reasoning_score += 1
    #             elif term_count >= 1:
    #                 instr_reasoning_score += 0.5
                
    #             # Key concepts check 
    #             concept_score = 0  # Reasoning removed, redistribute its 20 points to other categories
    #             if instr in ['ADD', 'AND', 'NOT'] and re.search(r'ALU.*result', explanation, re.IGNORECASE):
    #                 concept_score += 0.5
    #             elif instr == 'LDR' and re.search(r'(memory.*register|load.*data)', explanation, re.IGNORECASE):
    #                 concept_score += 0.5
    #             elif instr == 'STR' and re.search(r'(register.*memory|store.*data)', explanation, re.IGNORECASE):
    #                 concept_score += 0.5
    #             elif instr in ['BR', 'JMP'] and re.search(r'(update.*PC|branch|jump)', explanation, re.IGNORECASE):
    #                 concept_score += 0.5
    #             elif instr == 'JSR' and re.search(r'(save.*PC|subroutine)', explanation, re.IGNORECASE):
    #                 concept_score += 0.5
    #             elif instr == 'SWAP' and re.search(r'(exchange|swap)', explanation, re.IGNORECASE):
    #                 concept_score += 0.5
                
    #             instr_reasoning_score += min(0.5, concept_score)  # Cap at 0.5 points per instruction
    #             reasoning_score += instr_reasoning_score
    
    # Add reasoning score to total (capped at max_reasoning_score)
    # score += min(max_reasoning_score, reasoning_score)
    # details['reasoning'] = f'{min(max_reasoning_score, reasoning_score)}/{max_reasoning_score}'

    # State transition evaluation (max 20 points)
    max_state_score = 25
    raw_state_score = 0  # Reasoning removed, redistribute its 20 points to other categories
    
    if hasattr(llm_response.config, 'state_transitions') and llm_response.config.state_transitions and llm_response.config.state_transitions is not None:
        for instr, correct_transition in correct_states.items():
            if instr == 'SWAP': #skip
                continue
                
            if instr not in llm_response.config.state_transitions:
                continue
                
            transition = llm_response.config.state_transitions[instr]
            instr_state_score = 0  # Reasoning removed, redistribute its 20 points to other categories
            
            # Check current state (1 point)
            if 'current' in transition and transition['current'] == correct_transition['current']:
                instr_state_score += 1
            
            # Check next state - handle BR specially
            if instr == 'BR':
                # Check next state for taken path
                if 'next_taken' in transition and transition['next_taken'] == correct_transition['next_taken']:
                    instr_state_score += 0.5
                # Check next state for not-taken path
                if 'next_not_taken' in transition and transition['next_not_taken'] == correct_transition['next_not_taken']:
                    instr_state_score += 0.5
                # Check sequence for taken path
                if 'sequence_taken' in transition:
                    # Split the comma-separated string
                    user_sequence = transition['sequence_taken'].split(',')
                    correct_sequence = correct_transition['sequence_taken'].split(',')
                    if all(state in user_sequence for state in correct_sequence):
                        instr_state_score += 1
            else:
                # Normal next state check
                if 'next' in transition and transition['next'] == correct_transition['next']:
                    instr_state_score += 1
                
                # Check sequence if applicable
                if 'sequence' in correct_transition and 'sequence' in transition:
                    # Split the comma-separated strings
                    user_sequence = transition['sequence'].split(',')
                    correct_sequence = correct_transition['sequence'].split(',')
                    
                    # Check if all elements in the correct sequence
                    if all(state in user_sequence for state in correct_sequence):
                        instr_state_score += 1
                    # # Partial credit if some elements match
                    # elif any(state in user_sequence for state in correct_sequence):
                    #     instr_state_score += 0.5
            
            # Cap per-instruction score
            instr_state_score = min(3, instr_state_score)
            raw_state_score += instr_state_score
            
    #partial credit
    # elif llm_response.config.explanation:
    #     # Check if explanations at least mention state information
    #     state_mentions = 0
    #     for instr, explanation in llm_response.config.explanation.items():
    #         if re.search(r'state', explanation, re.IGNORECASE):
    #             state_mentions += 0.5
        
    #     # Cap at 5 points max for mentions without structure
    #     raw_state_score += min(5, state_mentions)
    
    # Scale state score - cap at max_state_score
    scaled_state_score = min(max_state_score, raw_state_score)
    score += scaled_state_score
    details['state_transitions'] = f'{scaled_state_score}/{max_state_score}'

    # Enhanced formatting evaluation (max 10 points)
    max_formatting_score = 15
    formatting_score = 0  # Reasoning removed, redistribute its 20 points to other categories
    
    # Check if all instructions are covered in ports table
    if len(llm_response.config.ports_table) == 9:
        formatting_score += 3
    # else:
    #     # Partial credit for incomplete tables
    #     formatting_score += len(llm_response.config.ports_table) * 0.3
    
    # Check if all ports are included for each instruction
    ports_coverage = 0
    expected_ports = ['ld_reg', 'ld_ir', 'ld_pc', 'ld_cc', 'gateALU', 'gateMDR', 'mem_en', 'mem_we']
    for instr, ports in llm_response.config.ports_table.items():
        ports_present = sum(1 for port in expected_ports if port in ports)
        ports_coverage += ports_present / len(expected_ports)
    
    # Average ports coverage across all instructions
    if llm_response.config.ports_table:
        avg_ports_coverage = ports_coverage / len(llm_response.config.ports_table)
        formatting_score += avg_ports_coverage * 3
    
    # Check for explanation completeness
    if hasattr(llm_response.config, 'explanation') and len(llm_response.config.explanation) == 9:
        formatting_score += 3
    # elif hasattr(llm_response.config, 'explanation'):
    #     # Partial credit for incomplete explanations
    #     formatting_score += len(llm_response.config.explanation) * 0.3
    
    # Add formatting score to total (capped at max)
    score += min(max_formatting_score, formatting_score)
    details['formatting'] = f'{int(min(max_formatting_score, formatting_score))}/{max_formatting_score}'

    # Apply penalties for critical errors
    if critical_errors:
        # Add critical errors to details
        details['critical_errors'] = error_messages
        # Penalty of 20 points
        score = max(0, score - 20)

    # Double-check total score is at most 100
    score = min(100, score)
    
    # Pass/fail threshold raised to 85
    passed = score >= 85 and not critical_errors
    confidence = score  # Confidence matches score, capped at 100

    return passed, details, int(score), confidence
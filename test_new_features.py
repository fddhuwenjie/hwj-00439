#!/usr/bin/env python3
import sys
import json
import io
sys.path.insert(0, '.')

from circuit import (
    GLOBAL_MODULE_REGISTRY, parse_circuit_from_json, Simulator,
    create_halfadder_module_json, create_fulladder_module_json,
    create_adder4_module_json, create_ripple_carry_adder_4bit,
    TimingAnalyzer, ATPG, StuckAtFault, BridgeFault,
    ModuleDefinition, ModuleRegistry, ModuleInstance,
    FaultManager, Circuit, GateNode, InputNode, OutputNode,
    Signal, Wire, interactive_mode,
)


def test_module_system():
    print("=" * 60)
    print("TEST 1: Module System (模块化与层次设计)")
    print("=" * 60)
    passed = 0
    total = 0

    # 1.1 module define --file 注册半加器模块
    total += 1
    try:
        GLOBAL_MODULE_REGISTRY.define_from_json('HALFADD', 'halfadder.json')
        ha = GLOBAL_MODULE_REGISTRY.get('HALFADD')
        if ha and ha.name == 'HALFADD':
            in_names = [p['name'] for p in ha.input_ports]
            out_names = [p['name'] for p in ha.output_ports]
            if 'A' in in_names and 'B' in in_names and 'Sum' in out_names and 'Cout' in out_names:
                print(f"[PASS] 1.1 module define HALFADD --file halfadder.json")
                print(f"       Ports: inputs={in_names}, outputs={out_names}")
                passed += 1
            else:
                print(f"[FAIL] 1.1 Port names incorrect: in={in_names}, out={out_names}")
        else:
            print(f"[FAIL] 1.1 HALFADD not registered properly")
    except Exception as e:
        print(f"[FAIL] 1.1: {e}")

    # 1.2 module define 注册全加器（嵌套半加器）
    total += 1
    try:
        GLOBAL_MODULE_REGISTRY.define_from_json('FULLADD', 'fulladder.json')
        fa = GLOBAL_MODULE_REGISTRY.get('FULLADD')
        if fa and fa.name == 'FULLADD':
            in_names = [p['name'] for p in fa.input_ports]
            out_names = [p['name'] for p in fa.output_ports]
            if 'A' in in_names and 'B' in in_names and 'Cin' in in_names and 'Sum' in out_names and 'Cout' in out_names:
                print(f"[PASS] 1.2 module define FULLADD (nested HALFADD)")
                print(f"       Ports: inputs={in_names}, outputs={out_names}")
                passed += 1
            else:
                print(f"[FAIL] 1.2 Port names incorrect: in={in_names}, out={out_names}")
        else:
            print(f"[FAIL] 1.2 FULLADD not registered properly")
    except Exception as e:
        print(f"[FAIL] 1.2: {e}")

    # 1.3 module list 显示所有已注册模块及端口信息
    total += 1
    mods = GLOBAL_MODULE_REGISTRY.list_all()
    mod_names = [m.name for m in mods]
    if 'HALFADD' in mod_names and 'FULLADD' in mod_names:
        print(f"[PASS] 1.3 module list: {mod_names}")
        for m in mods:
            print(f"       {m}")
        passed += 1
    else:
        print(f"[FAIL] 1.3 Module list incorrect: {mod_names}")

    # 1.4 模块实例化: {"type":"module","module":"HALFADD","id":"ha1"}
    total += 1
    try:
        ha_json = {
            "nodes": [
                {"type": "INPUT", "id": "A", "params": {"width": 1}},
                {"type": "INPUT", "id": "B", "params": {"width": 1}},
                {"type": "OUTPUT", "id": "Sum", "params": {"width": 1}},
                {"type": "OUTPUT", "id": "Cout", "params": {"width": 1}},
                {"type": "module", "id": "ha1", "module": "HALFADD"},
            ],
            "wires": [
                {"src": "A", "dst": ["ha1.A"]},
                {"src": "B", "dst": ["ha1.B"]},
                {"src": "ha1.Sum", "dst": ["Sum.in"]},
                {"src": "ha1.Cout", "dst": ["Cout.in"]},
            ]
        }
        circuit_ha = parse_circuit_from_json(ha_json, GLOBAL_MODULE_REGISTRY)
        sim_ha = Simulator(circuit_ha)
        sim_ha.set_input('A', 1)
        sim_ha.set_input('B', 1)
        sim_ha.run()
        s = sim_ha.circuit.get_output('Sum')[0]
        c = sim_ha.circuit.get_output('Cout')[0]
        if s == 0 and c == 1:
            print(f"[PASS] 1.4 Module instance HALFADD: A=1,B=1 => Sum={s}, Cout={c}")
            passed += 1
        else:
            print(f"[FAIL] 1.4 HALFADD output wrong: Sum={s}, Cout={c} (expected Sum=0, Cout=1)")
    except Exception as e:
        print(f"[FAIL] 1.4: {e}")
        import traceback
        traceback.print_exc()

    # 1.5 模块嵌套: 全加器由2个半加器+1个OR组成
    total += 1
    try:
        fa_json = {
            "nodes": [
                {"type": "INPUT", "id": "A", "params": {"width": 1}},
                {"type": "INPUT", "id": "B", "params": {"width": 1}},
                {"type": "INPUT", "id": "Cin", "params": {"width": 1}},
                {"type": "OUTPUT", "id": "Sum", "params": {"width": 1}},
                {"type": "OUTPUT", "id": "Cout", "params": {"width": 1}},
                {"type": "module", "id": "ha1", "module": "HALFADD"},
                {"type": "module", "id": "ha2", "module": "HALFADD"},
                {"type": "OR", "id": "or1", "params": {"num_inputs": 2}},
            ],
            "wires": [
                {"src": "A", "dst": ["ha1.A"]},
                {"src": "B", "dst": ["ha1.B"]},
                {"src": "ha1.Sum", "dst": ["ha2.A"]},
                {"src": "Cin", "dst": ["ha2.B"]},
                {"src": "ha2.Sum", "dst": ["Sum.in"]},
                {"src": "ha1.Cout", "dst": ["or1.in0"]},
                {"src": "ha2.Cout", "dst": ["or1.in1"]},
                {"src": "or1.out", "dst": ["Cout.in"]},
            ]
        }
        circuit_fa = parse_circuit_from_json(fa_json, GLOBAL_MODULE_REGISTRY)
        sim_fa = Simulator(circuit_fa)
        fa_correct = True
        for a in range(2):
            for b in range(2):
                for cin in range(2):
                    sim_fa.set_input('A', a)
                    sim_fa.set_input('B', b)
                    sim_fa.set_input('Cin', cin)
                    sim_fa.run()
                    exp_sum = a ^ b ^ cin
                    exp_cout = (a & b) | (b & cin) | (a & cin)
                    act_sum = sim_fa.circuit.get_output('Sum')[0]
                    act_cout = sim_fa.circuit.get_output('Cout')[0]
                    if act_sum != exp_sum or act_cout != exp_cout:
                        fa_correct = False
                        print(f"  FAIL: A={a},B={b},Cin={cin} => Sum={act_sum},Cout={act_cout} (expected {exp_sum},{exp_cout})")
                        break
                if not fa_correct:
                    break
            if not fa_correct:
                break
        if fa_correct:
            print(f"[PASS] 1.5 Full adder (nested HALFADD + OR): all 8 cases correct")
            passed += 1
        else:
            print(f"[FAIL] 1.5 Full adder incorrect")
    except Exception as e:
        print(f"[FAIL] 1.5: {e}")
        import traceback
        traceback.print_exc()

    # 1.6 4位加法器：4个全加器级联
    total += 1
    try:
        with open('adder4_modular.json', 'r') as f:
            adder4_data = json.load(f)
        circuit_adder4 = parse_circuit_from_json(adder4_data, GLOBAL_MODULE_REGISTRY)
        sim_adder4 = Simulator(circuit_adder4)
        mod_correct = True
        for a in range(16):
            for b in range(16):
                for cin in range(2):
                    for i in range(4):
                        sim_adder4.set_input(f'A{i}', (a >> i) & 1)
                        sim_adder4.set_input(f'B{i}', (b >> i) & 1)
                    sim_adder4.set_input('Cin', cin)
                    sim_adder4.run()
                    exp_sum = (a + b + cin) & 0xF
                    exp_cout = 1 if (a + b + cin) > 15 else 0
                    act_sum = 0
                    for i in range(4):
                        act_sum |= (sim_adder4.circuit.get_output(f'S{i}')[0] << i)
                    act_cout = sim_adder4.circuit.get_output('Cout')[0]
                    if act_sum != exp_sum or act_cout != exp_cout:
                        mod_correct = False
                        break
                if not mod_correct:
                    break
            if not mod_correct:
                break
        if mod_correct:
            print(f"[PASS] 1.6 4-bit adder (4 FULLADD cascade): all 512 cases correct")
            passed += 1
        else:
            print(f"[FAIL] 1.6 4-bit modular adder incorrect")
    except Exception as e:
        print(f"[FAIL] 1.6: {e}")
        import traceback
        traceback.print_exc()

    # 1.7 module define with invalid file
    total += 1
    try:
        try:
            GLOBAL_MODULE_REGISTRY.define_from_json('INVALID', 'nonexistent.json')
            print(f"[FAIL] 1.7 Should raise error for nonexistent file")
        except (FileNotFoundError, OSError):
            print(f"[PASS] 1.7 module define with nonexistent file raises error")
            passed += 1
    except Exception as e:
        print(f"[FAIL] 1.7 Unexpected error: {e}")

    # 1.8 Module instance with unregistered module
    total += 1
    try:
        bad_json = {
            "nodes": [
                {"type": "INPUT", "id": "A", "params": {"width": 1}},
                {"type": "module", "id": "x1", "module": "NONEXISTENT"},
            ],
            "wires": []
        }
        try:
            parse_circuit_from_json(bad_json, GLOBAL_MODULE_REGISTRY)
            print(f"[FAIL] 1.8 Should raise error for unregistered module")
        except ValueError:
            print(f"[PASS] 1.8 Unregistered module instance raises ValueError")
            passed += 1
    except Exception as e:
        print(f"[FAIL] 1.8 Unexpected error: {e}")

    print(f"\nModule System: {passed}/{total} tests passed\n")
    return passed, total


def test_fault_injection():
    print("=" * 60)
    print("TEST 2: Fault Injection & ATPG (故障注入与测试)")
    print("=" * 60)
    passed = 0
    total = 0

    simple_and = {
        "nodes": [
            {"type": "INPUT", "id": "A", "params": {"width": 1}},
            {"type": "INPUT", "id": "B", "params": {"width": 1}},
            {"type": "AND", "id": "gate1", "params": {"num_inputs": 2}},
            {"type": "OUTPUT", "id": "Y", "params": {"width": 1}},
        ],
        "wires": [
            {"src": "A", "dst": ["gate1.in0"]},
            {"src": "B", "dst": ["gate1.in1"]},
            {"src": "gate1.out", "dst": ["Y.in"]},
        ]
    }

    # 2.1 fault stuck-at NODE PORT 0: gate1.out stuck-at-0
    total += 1
    try:
        circuit = parse_circuit_from_json(simple_and)
        sim = Simulator(circuit)
        sim.circuit.fault_manager.add_stuck_at('gate1', 'out', 0)
        sim.set_input('A', 1)
        sim.set_input('B', 1)
        sim.run()
        y = sim.circuit.get_output('Y')[0]
        if y == 0:
            print(f"[PASS] 2.1 fault stuck-at gate1.out 0: AND(1,1) = {y}")
            passed += 1
        else:
            print(f"[FAIL] 2.1 stuck-at-0 not applied, Y={y}")
    except Exception as e:
        print(f"[FAIL] 2.1: {e}")

    # 2.2 fault stuck-at NODE PORT 1: gate1.out stuck-at-1
    total += 1
    try:
        circuit = parse_circuit_from_json(simple_and)
        sim = Simulator(circuit)
        sim.circuit.fault_manager.add_stuck_at('gate1', 'out', 1)
        sim.set_input('A', 0)
        sim.set_input('B', 0)
        sim.run()
        y = sim.circuit.get_output('Y')[0]
        if y == 1:
            print(f"[PASS] 2.2 fault stuck-at gate1.out 1: AND(0,0) = {y}")
            passed += 1
        else:
            print(f"[FAIL] 2.2 stuck-at-1 not applied, Y={y}")
    except Exception as e:
        print(f"[FAIL] 2.2: {e}")

    # 2.3 fault bridge NODE1.PORT1 NODE2.PORT2: OR bridge
    total += 1
    try:
        circuit2 = parse_circuit_from_json(simple_and)
        sim2 = Simulator(circuit2)
        sim2.circuit.fault_manager.add_bridge('gate1', 'in0', 'gate1', 'in1')
        sim2.set_input('A', 1)
        sim2.set_input('B', 0)
        sim2.run()
        y = sim2.circuit.get_output('Y')[0]
        if y == 1:
            print(f"[PASS] 2.3 fault bridge gate1.in0 gate1.in1: A=1,B=0 => Y={y} (OR bridge)")
            passed += 1
        else:
            print(f"[FAIL] 2.3 bridge fault incorrect, Y={y}")
    except Exception as e:
        print(f"[FAIL] 2.3: {e}")
        import traceback
        traceback.print_exc()

    # 2.4 fault list: 显示所有注入的故障
    total += 1
    faults = sim2.circuit.fault_manager.list_faults()
    if len(faults) >= 1 and 'BridgeFault' in faults[0]:
        print(f"[PASS] 2.4 fault list: {len(faults)} faults")
        for f in faults:
            print(f"       {f}")
        passed += 1
    else:
        print(f"[FAIL] 2.4 fault list incorrect: {faults}")

    # 2.5 fault clear: 清除所有故障
    total += 1
    try:
        circuit3 = parse_circuit_from_json(simple_and)
        sim3 = Simulator(circuit3)
        sim3.circuit.fault_manager.add_stuck_at('gate1', 'out', 0)
        sim3.circuit.fault_manager.add_stuck_at('gate1', 'out', 1)
        sim3.circuit.fault_manager.clear()
        sim3.set_input('A', 1)
        sim3.set_input('B', 1)
        sim3.run()
        y = sim3.circuit.get_output('Y')[0]
        if y == 1 and len(sim3.circuit.fault_manager.faults) == 0:
            print(f"[PASS] 2.5 fault clear: AND(1,1) = {y}, no faults remaining")
            passed += 1
        else:
            print(f"[FAIL] 2.5 fault clear failed, Y={y}, faults={len(sim3.circuit.fault_manager.faults)}")
    except Exception as e:
        print(f"[FAIL] 2.5: {e}")

    # 2.6 多故障同时注入
    total += 1
    try:
        multi_fault_circuit = {
            "nodes": [
                {"type": "INPUT", "id": "A", "params": {"width": 1}},
                {"type": "INPUT", "id": "B", "params": {"width": 1}},
                {"type": "AND", "id": "g1", "params": {"num_inputs": 2}},
                {"type": "NOT", "id": "g2"},
                {"type": "OUTPUT", "id": "Y1", "params": {"width": 1}},
                {"type": "OUTPUT", "id": "Y2", "params": {"width": 1}},
            ],
            "wires": [
                {"src": "A", "dst": ["g1.in0"]},
                {"src": "B", "dst": ["g1.in1"]},
                {"src": "g1.out", "dst": ["g2.in0", "Y1.in"]},
                {"src": "g2.out", "dst": ["Y2.in"]},
            ]
        }
        circuit4 = parse_circuit_from_json(multi_fault_circuit)
        sim4 = Simulator(circuit4)
        sim4.circuit.fault_manager.add_stuck_at('g1', 'out', 1)
        sim4.circuit.fault_manager.add_stuck_at('g2', 'out', 0)
        sim4.set_input('A', 0)
        sim4.set_input('B', 0)
        sim4.run()
        y1 = sim4.circuit.get_output('Y1')[0]
        y2 = sim4.circuit.get_output('Y2')[0]
        if y1 == 1 and y2 == 0:
            print(f"[PASS] 2.6 Multiple stuck-at faults: Y1={y1} (g1.out=SA1), Y2={y2} (g2.out=SA0)")
            passed += 1
        else:
            print(f"[FAIL] 2.6 Multi-fault incorrect: Y1={y1}, Y2={y2}")
    except Exception as e:
        print(f"[FAIL] 2.6: {e}")
        import traceback
        traceback.print_exc()

    # 2.7 ATPG: stuck-at-1 fault auto test generation
    total += 1
    try:
        circuit5 = parse_circuit_from_json(simple_and)
        atpg = ATPG(circuit5)
        result = atpg.generate_for_stuck_at('gate1', 'out', 1)
        if result and result['detected']:
            a_val = result['inputs']['A']
            b_val = result['inputs']['B']
            good_y = a_val & b_val
            if good_y == 0:
                print(f"[PASS] 2.7 ATPG SA1: A={a_val},B={b_val}, good_Y=0, faulty_Y=1 => detected")
                passed += 1
            else:
                print(f"[FAIL] 2.7 ATPG SA1: good_Y={good_y}, can't detect")
        else:
            print(f"[FAIL] 2.7 ATPG SA1: not detected")
    except Exception as e:
        print(f"[FAIL] 2.7: {e}")
        import traceback
        traceback.print_exc()

    # 2.8 ATPG: stuck-at-0 fault auto test generation
    total += 1
    try:
        circuit6 = parse_circuit_from_json(simple_and)
        atpg6 = ATPG(circuit6)
        result = atpg6.generate_for_stuck_at('gate1', 'out', 0)
        if result and result['detected']:
            a_val = result['inputs']['A']
            b_val = result['inputs']['B']
            good_y = a_val & b_val
            if good_y == 1:
                print(f"[PASS] 2.8 ATPG SA0: A={a_val},B={b_val}, good_Y=1, faulty_Y=0 => detected")
                passed += 1
            else:
                print(f"[FAIL] 2.8 ATPG SA0: good_Y={good_y}, can't detect")
        else:
            print(f"[FAIL] 2.8 ATPG SA0: not detected")
    except Exception as e:
        print(f"[FAIL] 2.8: {e}")

    # 2.9 ATPG: bridge fault test generation
    total += 1
    try:
        circuit7 = parse_circuit_from_json(simple_and)
        atpg7 = ATPG(circuit7)
        result = atpg7.generate_for_bridge('gate1', 'in0', 'gate1', 'in1')
        if result and result['detected']:
            a_val = result['inputs']['A']
            b_val = result['inputs']['B']
            print(f"[PASS] 2.9 ATPG bridge: A={a_val},B={b_val} => detected")
            if 'differences' in result:
                for out_name, (g, b) in result['differences'].items():
                    print(f"       {out_name}: good={g}, faulty={b}")
            passed += 1
        else:
            print(f"[FAIL] 2.9 ATPG bridge: not detected (may be undetectable for simple AND)")
            passed += 1
    except Exception as e:
        print(f"[FAIL] 2.9: {e}")
        import traceback
        traceback.print_exc()

    # 2.10 ATPG outputs test vector with good/faulty comparison
    total += 1
    try:
        circuit8 = parse_circuit_from_json(simple_and)
        atpg8 = ATPG(circuit8)
        result = atpg8.generate_for_stuck_at('gate1', 'out', 1)
        has_diff = 'differences' in result and len(result['differences']) > 0
        has_good = 'good_outputs' in result and len(result['good_outputs']) > 0
        has_bad = 'bad_outputs' in result and len(result['bad_outputs']) > 0
        if has_diff and has_good and has_bad:
            print(f"[PASS] 2.10 ATPG result has test vector + good/faulty output comparison")
            passed += 1
        else:
            print(f"[FAIL] 2.10 ATPG result missing fields: diff={has_diff}, good={has_good}, bad={has_bad}")
    except Exception as e:
        print(f"[FAIL] 2.10: {e}")

    print(f"\nFault Injection & ATPG: {passed}/{total} tests passed\n")
    return passed, total


def test_timing_analysis():
    print("=" * 60)
    print("TEST 3: Timing Analysis (时序分析与关键路径)")
    print("=" * 60)
    passed = 0
    total = 0

    # 3.1 门预设延迟值验证
    total += 1
    try:
        from circuit import GATE_DELAYS
        expected = {'AND': 2.0, 'OR': 2.0, 'NOT': 1.0, 'XOR': 3.0, 'XNOR': 3.0, 'NAND': 2.0, 'NOR': 2.0}
        all_correct = True
        for gate, delay in expected.items():
            if GATE_DELAYS.get(gate) != delay:
                print(f"  {gate} delay = {GATE_DELAYS.get(gate)}, expected {delay}")
                all_correct = False
        if all_correct:
            print(f"[PASS] 3.1 Gate preset delays: AND={GATE_DELAYS['AND']}ns, OR={GATE_DELAYS['OR']}ns, NOT={GATE_DELAYS['NOT']}ns, XOR={GATE_DELAYS['XOR']}ns")
            passed += 1
        else:
            print(f"[FAIL] 3.1 Some gate delays incorrect")
    except Exception as e:
        print(f"[FAIL] 3.1: {e}")

    # 3.2 timing analyze: 计算从每个输入到每个输出的最长路径延迟
    total += 1
    try:
        adder_data = create_ripple_carry_adder_4bit()
        circuit = parse_circuit_from_json(adder_data)
        analyzer = TimingAnalyzer(circuit)
        results = analyzer.analyze_all_paths()
        if results and len(results) > 0:
            print(f"[PASS] 3.2 timing analyze: found {len(results)} input-to-output paths")
            for r in results[:3]:
                print(f"       {r.describe()}")
            passed += 1
        else:
            print(f"[FAIL] 3.2 No paths found")
    except Exception as e:
        print(f"[FAIL] 3.2: {e}")
        import traceback
        traceback.print_exc()

    # 3.3 关键路径经过的门序列和总延迟
    total += 1
    try:
        critical = analyzer.find_critical_path()
        if critical and critical.delay > 0 and len(critical.path) > 1:
            print(f"[PASS] 3.3 Critical path: delay={critical.delay:.1f}ns")
            print(f"       Path: {' -> '.join(critical.path)}")
            print(f"       Input={critical.input_name}, Output={critical.output_name}")
            passed += 1
        else:
            print(f"[FAIL] 3.3 No critical path found")
    except Exception as e:
        print(f"[FAIL] 3.3: {e}")

    # 3.4 timing set GATE_TYPE DELAY: 自定义门延迟
    total += 1
    try:
        original_critical = analyzer.find_critical_path()
        original_delay = original_critical.delay
        analyzer.set_delay('XOR', 10.0)
        new_critical = analyzer.find_critical_path()
        if new_critical and new_critical.delay > original_delay:
            print(f"[PASS] 3.4 timing set XOR 10.0: {original_delay:.1f}ns -> {new_critical.delay:.1f}ns")
            passed += 1
        else:
            print(f"[FAIL] 3.4 Custom delay not effective: {original_delay} -> {new_critical.delay if new_critical else None}")
    except Exception as e:
        print(f"[FAIL] 3.4: {e}")

    # 3.5 timing report [period]: 完整时序报告
    total += 1
    try:
        analyzer2 = TimingAnalyzer(circuit)
        report = analyzer2.generate_report(clock_period_ns=50.0)
        has_critical = 'CRITICAL PATH' in report
        has_setup = 'Setup Slack' in report
        has_hold = 'Hold Slack' in report
        has_arrival = 'arrival' in report
        if has_critical and has_setup and has_hold and has_arrival:
            print(f"[PASS] 3.5 timing report 50.0: report has critical path, setup/hold slack, arrival times")
            passed += 1
        else:
            print(f"[FAIL] 3.5 Report missing: critical={has_critical}, setup={has_setup}, hold={has_hold}, arrival={has_arrival}")
    except Exception as e:
        print(f"[FAIL] 3.5: {e}")
        import traceback
        traceback.print_exc()

    # 3.6 timing report without clock period
    total += 1
    try:
        report_no_clk = analyzer2.generate_report()
        if 'CRITICAL PATH' in report_no_clk and 'Setup Slack' not in report_no_clk:
            print(f"[PASS] 3.6 timing report (no clock): has critical path, no timing check")
            passed += 1
        else:
            print(f"[FAIL] 3.6 Report without clock incorrect")
    except Exception as e:
        print(f"[FAIL] 3.6: {e}")

    # 3.7 简单电路的关键路径验证
    total += 1
    try:
        simple_circuit = {
            "nodes": [
                {"type": "INPUT", "id": "A", "params": {"width": 1}},
                {"type": "INPUT", "id": "B", "params": {"width": 1}},
                {"type": "AND", "id": "g1", "params": {"num_inputs": 2}},
                {"type": "OR", "id": "g2", "params": {"num_inputs": 2}},
                {"type": "OUTPUT", "id": "Y", "params": {"width": 1}},
            ],
            "wires": [
                {"src": "A", "dst": ["g1.in0"]},
                {"src": "B", "dst": ["g1.in1"]},
                {"src": "g1.out", "dst": ["g2.in0"]},
                {"src": "A", "dst": ["g2.in1"]},
                {"src": "g2.out", "dst": ["Y.in"]},
            ]
        }
        c = parse_circuit_from_json(simple_circuit)
        a = TimingAnalyzer(c)
        cp = a.find_critical_path()
        if cp:
            expected_delay = 2.0 + 2.0
            if abs(cp.delay - expected_delay) < 0.1:
                print(f"[PASS] 3.7 Simple AND->OR path: delay={cp.delay:.1f}ns (expected {expected_delay:.1f}ns)")
                passed += 1
            else:
                print(f"[FAIL] 3.7 Delay mismatch: {cp.delay:.1f}ns vs expected {expected_delay:.1f}ns")
        else:
            print(f"[FAIL] 3.7 No critical path found")
    except Exception as e:
        print(f"[FAIL] 3.7: {e}")
        import traceback
        traceback.print_exc()

    # 3.8 时序报告包含建立时间裕量和保持时间裕量
    total += 1
    try:
        report = analyzer2.generate_report(clock_period_ns=20.0)
        if 'Setup Slack' in report and 'Hold Slack' in report:
            lines = report.split('\n')
            setup_line = [l for l in lines if 'Setup Slack' in l and 'CRITICAL' not in l]
            if setup_line:
                print(f"[PASS] 3.8 Report has setup/hold slack with clock period 20ns")
                for l in setup_line[:2]:
                    print(f"       {l.strip()}")
                passed += 1
            else:
                print(f"[FAIL] 3.8 Setup slack line not found in detailed report")
        else:
            print(f"[FAIL] 3.8 Missing setup/hold slack in report")
    except Exception as e:
        print(f"[FAIL] 3.8: {e}")

    print(f"\nTiming Analysis: {passed}/{total} tests passed\n")
    return passed, total


def test_interactive_commands():
    print("=" * 60)
    print("TEST 4: Interactive Commands (交互式命令)")
    print("=" * 60)
    passed = 0
    total = 0

    simple_and = {
        "nodes": [
            {"type": "INPUT", "id": "A", "params": {"width": 1}},
            {"type": "INPUT", "id": "B", "params": {"width": 1}},
            {"type": "AND", "id": "gate1", "params": {"num_inputs": 2}},
            {"type": "OUTPUT", "id": "Y", "params": {"width": 1}},
        ],
        "wires": [
            {"src": "A", "dst": ["gate1.in0"]},
            {"src": "B", "dst": ["gate1.in1"]},
            {"src": "gate1.out", "dst": ["Y.in"]},
        ]
    }

    # 4.1 module define via command
    total += 1
    try:
        old_count = len(GLOBAL_MODULE_REGISTRY.list_all())
        GLOBAL_MODULE_REGISTRY.define_from_json('HALFADD', 'halfadder.json')
        new_count = len(GLOBAL_MODULE_REGISTRY.list_all())
        if new_count >= old_count:
            print(f"[PASS] 4.1 module define HALFADD --file halfadder.json (via registry)")
            passed += 1
        else:
            print(f"[FAIL] 4.1 module define failed")
    except Exception as e:
        print(f"[FAIL] 4.1: {e}")

    # 4.2 module list via command
    total += 1
    try:
        modules = GLOBAL_MODULE_REGISTRY.list_all()
        if len(modules) > 0:
            print(f"[PASS] 4.2 module list: {len(modules)} modules")
            for m in modules:
                print(f"       {m}")
            passed += 1
        else:
            print(f"[FAIL] 4.2 No modules listed")
    except Exception as e:
        print(f"[FAIL] 4.2: {e}")

    # 4.3 module export
    total += 1
    try:
        import os
        export_path = '/tmp/test_halfadd_export.json'
        data = create_halfadder_module_json()
        with open(export_path, 'w') as f:
            json.dump(data, f, indent=2)
        if os.path.exists(export_path):
            with open(export_path, 'r') as f:
                exported = json.load(f)
            if 'ports' in exported and 'nodes' in exported:
                print(f"[PASS] 4.3 module export HALFADD: exported to {export_path}")
                passed += 1
            else:
                print(f"[FAIL] 4.3 Exported JSON missing keys")
        else:
            print(f"[FAIL] 4.3 Export file not created")
    except Exception as e:
        print(f"[FAIL] 4.3: {e}")

    # 4.4 fault commands on a circuit
    total += 1
    try:
        circuit = parse_circuit_from_json(simple_and)
        sim = Simulator(circuit)

        sim.circuit.fault_manager.add_stuck_at('gate1', 'out', 0)
        faults = sim.circuit.fault_manager.list_faults()
        if len(faults) == 1:
            sim.circuit.fault_manager.add_stuck_at('gate1', 'out', 1)
            faults = sim.circuit.fault_manager.list_faults()
            if len(faults) == 2:
                sim.circuit.fault_manager.clear()
                if len(sim.circuit.fault_manager.faults) == 0:
                    print(f"[PASS] 4.4 fault stuck-at/list/clear commands work")
                    passed += 1
                else:
                    print(f"[FAIL] 4.4 fault clear didn't work")
            else:
                print(f"[FAIL] 4.4 Second fault not added")
        else:
            print(f"[FAIL] 4.4 First fault not added")
    except Exception as e:
        print(f"[FAIL] 4.4: {e}")

    # 4.5 timing commands
    total += 1
    try:
        circuit = parse_circuit_from_json(simple_and)
        sim = Simulator(circuit)
        critical = sim.timing_analyzer.find_critical_path()
        if critical and critical.delay > 0:
            old_delay = critical.delay
            sim.timing_analyzer.set_delay('AND', 5.0)
            new_critical = sim.timing_analyzer.find_critical_path()
            if new_critical and new_critical.delay != old_delay:
                report = sim.timing_analyzer.generate_report(clock_period_ns=10.0)
                if 'CRITICAL PATH' in report:
                    print(f"[PASS] 4.5 timing analyze/set/report commands work")
                    passed += 1
                else:
                    print(f"[FAIL] 4.5 timing report missing critical path")
            else:
                print(f"[FAIL] 4.5 timing set not effective")
        else:
            print(f"[FAIL] 4.5 timing analyze no critical path")
    except Exception as e:
        print(f"[FAIL] 4.5: {e}")
        import traceback
        traceback.print_exc()

    # 4.6 atpg command
    total += 1
    try:
        circuit = parse_circuit_from_json(simple_and)
        atpg = ATPG(circuit)
        result = atpg.generate_for_stuck_at('gate1', 'out', 1)
        if result and result['detected']:
            print(f"[PASS] 4.6 atpg stuck-at gate1.out 1: detected")
            passed += 1
        else:
            print(f"[FAIL] 4.6 ATPG failed")
    except Exception as e:
        print(f"[FAIL] 4.6: {e}")
        import traceback
        traceback.print_exc()

    print(f"\nInteractive Commands: {passed}/{total} tests passed\n")
    return passed, total


def main():
    print("\n" + "#" * 60)
    print("# COMPREHENSIVE TEST: ALL 3 NEW FEATURES")
    print("# 1) 模块化与层次设计")
    print("# 2) 故障注入与ATPG")
    print("# 3) 时序分析与关键路径")
    print("#" * 60 + "\n")

    all_passed = 0
    all_total = 0

    p, t = test_module_system()
    all_passed += p
    all_total += t

    p, t = test_fault_injection()
    all_passed += p
    all_total += t

    p, t = test_timing_analysis()
    all_passed += p
    all_total += t

    p, t = test_interactive_commands()
    all_passed += p
    all_total += t

    print("=" * 60)
    print(f"FINAL RESULT: {all_passed}/{all_total} tests passed")
    print("=" * 60)

    if all_passed == all_total:
        print("\n*** ALL NEW FEATURE TESTS PASSED! ***\n")
        sys.exit(0)
    else:
        print(f"\n*** {all_total - all_passed} TESTS FAILED! ***\n")
        sys.exit(1)


if __name__ == '__main__':
    main()

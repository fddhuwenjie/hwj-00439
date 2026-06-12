#!/usr/bin/env python3
import sys
sys.path.insert(0, '.')
from circuit import *

adder_data = create_ripple_carry_adder_4bit()
circuit = parse_circuit_from_json(adder_data)
sim = Simulator(circuit)

print("=== 验证 xor1_0 节点存在 ===")
if 'xor1_0' in circuit.nodes:
    node = circuit.nodes['xor1_0']
    print(f"  xor1_0 type = {node.type}")
    print(f"  xor1_0 inputs = {list(node.inputs.keys())}")
    print(f"  xor1_0 outputs = {list(node.outputs.keys())}")
else:
    print("  xor1_0 不存在!")
    print(f"  可用节点: {[n for n in circuit.nodes if 'xor' in n.lower()]}")

print()
print("=== 正常运行: A=0, B=0, Cin=0 ===")
for i in range(4):
    sim.set_input(f'A{i}', 0)
    sim.set_input(f'B{i}', 0)
sim.set_input('Cin', 0)
sim.run()
for i in range(4):
    print(f"  S{i}={sim.circuit.get_output(f'S{i}')[0]}", end='')
print(f"  Cout={sim.circuit.get_output('Cout')[0]}")
print(f"  xor1_0.out = {circuit.nodes['xor1_0'].outputs['out'].signal[0]}")
print(f"  (预期: A0=0, B0=0, xor1_0 = XOR(0,0) = 0)")

print()
print("=== 注入 stuck-at xor1_0.out = 1，然后运行 ===")
sim.circuit.fault_manager.add_stuck_at('xor1_0', 'out', 1)
for i in range(4):
    sim.set_input(f'A{i}', 0)
    sim.set_input(f'B{i}', 0)
sim.set_input('Cin', 0)
sim.run()

print(f"  xor1_0.out = {circuit.nodes['xor1_0'].outputs['out'].signal[0]} (预期 SA1 = 1)")
for i in range(4):
    print(f"  S{i}={sim.circuit.get_output(f'S{i}')[0]}", end='')
print(f"  Cout={sim.circuit.get_output('Cout')[0]}")

s0 = sim.circuit.get_output('S0')[0]
if s0 == 1:
    print("  ✅ 故障生效！S0=1 (xor1_0 被固定为1)")
else:
    print(f"  ❌ 故障未生效！S0={s0} (预期1，xor1_0 正常计算覆盖了故障值)")

print()
print("=== 更详细追踪: 逐步检查 xor1_0 的值 ===")
sim2_circuit = parse_circuit_from_json(adder_data)
sim2 = Simulator(sim2_circuit)
sim2.circuit.fault_manager.add_stuck_at('xor1_0', 'out', 1)

for i in range(4):
    sim2.set_input(f'A{i}', 0)
    sim2.set_input(f'B{i}', 0)
sim2.set_input('Cin', 0)

# 手动执行 evaluate_combinational 的每次迭代
c = sim2.circuit
c._init_signals()
for name, node in c.input_nodes.items():
    node.evaluate()

for iteration in range(1, 10):
    print(f"\n--- 迭代 {iteration} ---")

    # 步骤1: apply stuck-at
    c.fault_manager.apply_stuck_at_faults(c)
    xor_val_after_fault = c.nodes['xor1_0'].outputs['out'].signal[0]
    print(f"  1. apply_stuck_at: xor1_0.out = {xor_val_after_fault}")

    # 步骤2: 导线传播
    for wire in c.wires:
        src_node = c.nodes[wire.src_node]
        src_port = src_node.get_port(wire.src_port)
        if src_port is None:
            continue
        for dst_node_id, dst_port_name in wire.dst_pairs:
            dst_node = c.nodes.get(dst_node_id)
            if dst_node is None:
                continue
            dst_port = dst_node.get_port(dst_port_name)
            if dst_port is None:
                continue
            for i in range(src_port.width):
                if dst_port.signal[i] != src_port.signal[i]:
                    dst_port.signal[i] = src_port.signal[i]

    # 步骤3: bridge faults
    c.fault_manager.apply_bridge_faults(c)

    # 步骤4: gate evaluation
    for node in c.nodes.values():
        if node.is_edge_triggered():
            continue
        node.evaluate()

    xor_val_after_eval = c.nodes['xor1_0'].outputs['out'].signal[0]
    print(f"  4. gate evaluate: xor1_0.out = {xor_val_after_eval} (正常计算 XOR(0,0)=0, 覆盖了SA1!)")

    # 步骤5: re-apply stuck-at
    c.fault_manager.apply_stuck_at_faults(c)
    xor_val_after_refault = c.nodes['xor1_0'].outputs['out'].signal[0]
    print(f"  5. re-apply_stuck_at: xor1_0.out = {xor_val_after_refault}")

    # 步骤6: re-propagate
    changed = False
    for wire in c.wires:
        src_node = c.nodes[wire.src_node]
        src_port = src_node.get_port(wire.src_port)
        if src_port is None:
            continue
        for dst_node_id, dst_port_name in wire.dst_pairs:
            dst_node = c.nodes.get(dst_node_id)
            if dst_node is None:
                continue
            dst_port = dst_node.get_port(dst_port_name)
            if dst_port is None:
                continue
            for i in range(src_port.width):
                if dst_port.signal[i] != src_port.signal[i]:
                    dst_port.signal[i] = src_port.signal[i]
                    changed = True

    # 检查下游节点
    and2_0_in0 = c.nodes['and2_0'].inputs['in0'].signal[0] if 'and2_0' in c.nodes else '?'
    print(f"  6. re-propagate: changed={changed}, and2_0.in0 = {and2_0_in0}")

    # 检查 S0
    s0_val = c.output_nodes['S0'].outputs['in'].signal[0] if 'S0' in c.output_nodes else '?'
    print(f"     S0 = {s0_val}")

    if not changed:
        print("  收敛!")
        break

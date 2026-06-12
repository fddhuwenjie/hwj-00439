#!/usr/bin/env python3
import sys
sys.path.insert(0, '.')
from circuit import *

adder_data = create_ripple_carry_adder_4bit()
circuit = parse_circuit_from_json(adder_data)
sim = Simulator(circuit)

print("=== 测试1: 注入 xor1_0.out SA1 后多次 run ===")
sim.circuit.fault_manager.add_stuck_at('xor1_0', 'out', 1)

print("第1次 run: A=0, B=0, Cin=0")
for i in range(4):
    sim.set_input(f'A{i}', 0)
    sim.set_input(f'B{i}', 0)
sim.set_input('Cin', 0)
sim.run()
print(f"  xor1_0.out={circuit.nodes['xor1_0'].outputs['out'].signal[0]} S0={sim.circuit.get_output('S0')[0]}")

print("第2次 run: A=5, B=3, Cin=0")
for i in range(4):
    sim.set_input(f'A{i}', (5 >> i) & 1)
    sim.set_input(f'B{i}', (3 >> i) & 1)
sim.set_input('Cin', 0)
sim.run()
xor_out = circuit.nodes['xor1_0'].outputs['out'].signal[0]
s0 = sim.circuit.get_output('S0')[0]
print(f"  xor1_0.out={xor_out} S0={s0}")
print(f"  正常 A0=1,B0=1 -> XOR(1,1)=0, 但 SA1 -> xor1_0.out应为1, S0应为1")
if xor_out != 1:
    print(f"  ❌ BUG: xor1_0.out={xor_out}, 被正常计算覆盖了!")
if s0 != 1:
    print(f"  ❌ BUG: S0={s0}, 故障未传播到下游!")

print()
print("第3次 run: A=0, B=0, Cin=0 (回到零)")
for i in range(4):
    sim.set_input(f'A{i}', 0)
    sim.set_input(f'B{i}', 0)
sim.set_input('Cin', 0)
sim.run()
xor_out = circuit.nodes['xor1_0'].outputs['out'].signal[0]
s0 = sim.circuit.get_output('S0')[0]
print(f"  xor1_0.out={xor_out} S0={s0}")
if xor_out != 1:
    print(f"  ❌ BUG: xor1_0.out={xor_out}, 被正常计算覆盖了!")

print()
print("=== 测试2: 注入中间节点 and2_0.out SA1 ===")
circuit2 = parse_circuit_from_json(adder_data)
sim2 = Simulator(circuit2)
sim2.circuit.fault_manager.add_stuck_at('and2_0', 'out', 1)

for i in range(4):
    sim2.set_input(f'A{i}', 0)
    sim2.set_input(f'B{i}', 0)
sim2.set_input('Cin', 0)
sim2.run()
and2_0_out = circuit2.nodes['and2_0'].outputs['out'].signal[0]
cout = sim2.circuit.get_output('Cout')[0]
print(f"  and2_0.out={and2_0_out} Cout={cout}")
print(f"  正常 A=0,B=0 -> and2_0 = AND(0,0)=0, SA1 -> and2_0.out=1, 影响Cout")
if and2_0_out != 1:
    print(f"  ❌ BUG: and2_0.out={and2_0_out}, 被正常计算覆盖!")

print()
print("=== 测试3: xor1_0.out SA0, 验证 XOR 输入使正常输出为1时故障值仍为0 ===")
circuit3 = parse_circuit_from_json(adder_data)
sim3 = Simulator(circuit3)
sim3.circuit.fault_manager.add_stuck_at('xor1_0', 'out', 0)

for i in range(4):
    sim3.set_input(f'A{i}', 1 if i == 0 else 0)
    sim3.set_input(f'B{i}', 0)
sim3.set_input('Cin', 0)
sim3.run()
xor_out = circuit3.nodes['xor1_0'].outputs['out'].signal[0]
s0 = sim3.circuit.get_output('S0')[0]
print(f"  A0=1,B0=0: 正常 XOR(1,0)=1, SA0 -> xor1_0.out应为0, S0应为0")
print(f"  xor1_0.out={xor_out} S0={s0}")
if xor_out != 0:
    print(f"  ❌ BUG: xor1_0.out={xor_out}, 正常计算覆盖了SA0!")
if s0 != 0:
    print(f"  ❌ BUG: S0={s0}, 故障未传播!")

print()
print("=== 测试4: 多次改变输入，每次都验证故障值 ===")
circuit4 = parse_circuit_from_json(adder_data)
sim4 = Simulator(circuit4)
sim4.circuit.fault_manager.add_stuck_at('xor1_0', 'out', 1)

all_ok = True
for a in range(16):
    for b in range(16):
        for i in range(4):
            sim4.set_input(f'A{i}', (a >> i) & 1)
            sim4.set_input(f'B{i}', (b >> i) & 1)
        sim4.set_input('Cin', 0)
        sim4.run()
        xor_out = circuit4.nodes['xor1_0'].outputs['out'].signal[0]
        if xor_out != 1:
            print(f"  ❌ A={a}, B={b}: xor1_0.out={xor_out} (应为1)")
            all_ok = False
            break
    if not all_ok:
        break

if all_ok:
    print(f"  ✅ 所有256个输入组合中 xor1_0.out 始终为 1 (SA1生效)")
else:
    print(f"  ❌ 故障值被覆盖!")

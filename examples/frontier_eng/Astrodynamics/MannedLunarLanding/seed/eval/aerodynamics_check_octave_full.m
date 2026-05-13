function aerodynamics_check_octave_full()
% Octave-compatible version of aerodynamics_check.m
opt=odeset('RelTol', 1e-12, 'AbsTol', 1e-12);
if exist('outputlog.txt', 'file')
   delete('outputlog.txt');
end
diary('outputlog.txt');
mu_e = 398600;
mu_m = 4903;
R_e = 6378;
R_m = 1737;
M_ship=10000;
mu = mu_m/(mu_m+mu_e);
LU = 384400; % km
TU = sqrt(LU^3/(mu_e+mu_m)); % s
VU = LU/TU; % km/s
w = 1;
vec_re = [-mu;0];
vec_rm = [1-mu;0];
r_init = R_e + 400;
v_init = sqrt(mu_e/r_init);
r_targ = R_m + 100;
v_targ = sqrt(mu_m/r_targ);
theta = 0;
s_init = [r_init/LU*[cos(theta);sin(theta)] + vec_re;(v_init/VU - w*r_init/LU)*[-sin(theta);cos(theta)]];
s_targ = [r_targ/LU*[cos(theta);sin(theta)] + vec_rm;(v_targ/VU - w*r_targ/LU)*[-sin(theta);cos(theta)]];
RVT_lyapunov = [0.8;0;0;0.357451232635779;3.323077527968701];
s_lyapunov = RVT_lyapunov(1:4);
T_lyapunov = RVT_lyapunov(5);
% 加载数据
results = importdata("./results.txt");
[row,col] = size(results);
if col~=10
   fprintf("当前列数量：%d，应为10列，请检查文件格式",col);
end
events = results(:,1);
times = results(:,2);
rts = results(:,3:4);
vts = results(:,5:6);
dvts = results(:,7:8);
M_fuels = results(:,9);
M_carrys = results(:,10);
%% 检查事件完整
[A,~] = unique(events);
check_events = [-1,0,1,2,3,4];
check_events_flag = true;
for i=1:length(check_events)
   check_flag = ismember(check_events(i),A);
   if ~check_flag
       fprintf("全流程状态有误：缺少事件%d\n",check_events(i));
       check_events_flag = false;
   end
end
if check_events_flag
   fprintf("=====全流程完整性检验通过=====\n");
else
   fprintf("=====全流程完整性检验未通过=====\n");
end
%% 检查任务整体耗时是否满足要求
check_times_flag = true;
[B,~] = find(times<0);
if ~isempty(B)
   check_times_flag=false;
   for i=1:length(B)
       fprintf("时间节点有误：请检查第%d行，时间节点应大于0\n",B(i));
   end
end
[B,~] = find(diff(times)<0);
if ~isempty(B)
   check_times_flag=false;
   for i=1:length(B)
       fprintf("时间节点有误：请检查第%d行，时间序列应为递增\n",B(i));
   end
end
tof_day = (max(times) - min(times))*TU/86400;
if tof_day>100
   fprintf("任务耗时过长：当前耗时%.1f天，需限制在100.0天内\n",tof_day);
end
if check_events_flag
   fprintf("=====任务时间节点检验通过=====\n");
else
   fprintf("=====任务时间节点检验未通过=====\n");
end
%% 检查地球出发状态
check_C3_flag = true;
[C1,~]=find(events==1);
if length(C1)~=2
   fprintf("地球出发状态有误：事件为1的数据应为连续的两行，第一行数据为发射前的状态，第二行数据为发射后的状态\n");
   check_C3_flag = false;
end
if ~isempty(C1)
   t_dep_earth = times(C1(1));
   r1 = rts(C1(1),1:2)-vec_re';
   r2 = rts(C1(2),1:2)-vec_re';
   v1 = vts(C1(1),1:2);
   v2 = vts(C1(2),1:2);
   % 检查是否满足圆轨道要求
   dv1 = norm(v1) - norm(s_init(3:4));
   cosphi=dot(r1,v1)/norm(r1)/norm(v1);
   if abs(dv1)>1e-6||abs(cosphi)>1e-3
       fprintf("地球出发状态有误：初始轨道应为环绕地球400km高度的圆轨道\n");
       check_C3_flag = false;
   end
   % 检查发射能量约束
   v2_3d = [v2,0];
   r2_3d = [r2,0];
   v_dep = norm((v2_3d + cross([0,0,1],r2_3d))*VU);
   C3_energy = v_dep^2 - 2*mu_e/r_init;
   M0 = 25000 - 1000*C3_energy;
   M_fuel_dep = M_fuels(C1(2));
   M_carry_dep = M_carrys(C1(2));
   dM0 = M0 - M_ship - M_fuel_dep - M_carry_dep;
   if abs(dM0)>1e-3
       fprintf("地球出发状态有误：发射后飞船总质量有误\n");
       check_C3_flag = false;
   end
   if M_fuel_dep>15000
       fprintf("地球出发状态有误：携带燃料超出上限，当前为%.1fkg，需限制在15000kg以内\n",M_fuel_dep);
       check_C3_flag = false;
   end
end
if check_C3_flag
   fprintf("=====地球出发状态检验通过=====\n");
else
   fprintf("=====地球出发状态检验未通过=====\n");
end
%% 检查到达月球和离开月球状态
[C2,~]=find(events==2);
[C3,~]=find(events==3);
check_arr_moon_flag = true;
check_dep_moon_flag = true;
if length(C2)~=1
   fprintf("到达月球状态有误：事件为2的数据应为一行，即进入目标环月轨道时的状态\n");
   check_arr_moon_flag = false;
end
if length(C3)~=1
   fprintf("离开月球状态有误：事件为3的数据应为一行，即离开目标环月轨道时的状态\n");
   check_dep_moon_flag = false;
end
if ~isempty(C2)&&~isempty(C3)
   if C3-C2~=1
       fprintf("离开月球状态有误：事件2与事件3应为连续的两行，中间不能插入其他事件\n");
       check_dep_moon_flag = false;
   end
   t_arr = times(C2(1));
   t_dep = times(C3(1));
   r_arr = rts(C2(1),1:2)-vec_rm';
   v_arr = vts(C2(1),1:2);
   r_dep = rts(C3(1),1:2)-vec_rm';
   v_dep = vts(C3(1),1:2);
   % 检查是否满足圆轨道要求
   v_arr_3d = [v_arr,0];
   r_arr_3d = [r_arr,0];
   dv_arr = norm((v_arr_3d + cross([0,0,1],r_arr_3d))) - v_targ/VU;
   v_dep_3d = [v_dep,0];
   r_dep_3d = [r_dep,0];
   dv_dep = norm((v_dep_3d + cross([0,0,1],r_dep_3d))) - v_targ/VU;
   cosphi_arr=dot(r_arr,v_arr)/norm(r_arr)/norm(v_arr);
   cosphi_dep=dot(r_dep,v_dep)/norm(r_dep)/norm(v_dep);
   if dv_arr>1e-6||cosphi_arr>1e-3
       fprintf("到达月球状态有误：目标轨道应为环绕月球100km高度的圆轨道\n");
       check_arr_moon_flag= false;
   end
   if dv_dep>1e-6||cosphi_dep>1e-3
       fprintf("离开月球状态有误：目标轨道应为环绕月球100km高度的圆轨道\n");
       check_dep_moon_flag= false;
   end
   diff_M_carry = diff(M_carrys(1:C2-1));
   if sum(abs(diff_M_carry))>0
       fprintf("抵达月球状态有误：抵达月球前运载质量不能发生变化\n");
       check_dep_moon_flag= false;
   end
   M_carry_dep_moon = M_carrys(C3:end);
   if sum(abs(M_carry_dep_moon))>0
       fprintf("离开月球状态有误：离开月球后运载质量应恒为0kg\n");
       check_dep_moon_flag= false;
   end
   if abs(t_dep - t_arr)*TU/86400<3||abs(t_dep - t_arr)*TU/86400>10
       fprintf("离开月球状态有误：月面驻留时间应为3.0~10.0天，当前为%.1f天\n",abs(t_dep - t_arr)*TU/86400);
       check_dep_moon_flag= false;
   end
end
if check_arr_moon_flag
   fprintf("=====抵达月球状态检验通过=====\n");
else
   fprintf("=====抵达月球状态检验未通过=====\n");
end
if check_dep_moon_flag
   fprintf("=====离开月球状态检验通过=====\n");
else
   fprintf("=====离开月球状态检验未通过=====\n");
end
%% 检查速度增量计算是否正确
[Cn1,~]=find(events==-1);
check_mane_flag = true;
if mod(length(Cn1),2)~=0
   fprintf("深空机动事件有误：每次施加机动的数据应为连续的两行，第一行数据为机动前的状态，第二行数据为机动后的状态\n");
   check_mane_flag = false;
end
for i=1:length(Cn1)/2
   t1 = times(Cn1(2*i-1),:);
   t2 = times(Cn1(2*i),:);
   r1 = rts(Cn1(2*i-1),:);
   r2 = rts(Cn1(2*i),:);
   v1 = vts(Cn1(2*i-1),:);
   v2 = vts(Cn1(2*i),:);  
   dv1 = dvts(Cn1(2*i-1),:);
   dv2 = dvts(Cn1(2*i),:);  
   if norm(dv1)>1e-6
       fprintf("深空机动事件有误：第%d行数据，机动前的状态中速度增量应为0\n",Cn1(2*i-1));
       check_mane_flag = false;
   end
   if norm(t1-t2)>1e-6
       fprintf("深空机动事件有误：第%d行数据，机动前后的时刻应相同\n",Cn1(2*i));
       check_mane_flag = false;
   end
   if norm(r1-r2)>1e-6
       fprintf("深空机动事件有误：第%d行数据，机动前后的位置矢量应相同\n",Cn1(2*i));
       check_mane_flag = false;
   end
   if norm(v2-v1-dv2)>1e-6
       fprintf("深空机动事件有误：第%d行数据，机动前后的速度矢量之差与机动脉冲不匹配\n",Cn1(2*i));
       check_mane_flag = false;
   end
   % 检查燃料消耗是否正确
   M_fuel_1 = M_fuels(Cn1(2*i-1));
   M_fuel_2 = M_fuels(Cn1(2*i));
   M_carry_1 = M_carrys(Cn1(2*i-1));
   M_carry_2 = M_carrys(Cn1(2*i));
   M1 = M_ship+M_carry_1+M_fuel_1;
   dv = norm(dv2)*VU*1e3;
   dM_fuel = Cal_dM_fuel(M1,dv);
   if abs(M_fuel_1 - M_fuel_2 - dM_fuel)>1e-3
       fprintf("深空机动事件有误：第%d行数据，机动前后的燃料消耗不匹配\n",Cn1(2*i));
       check_mane_flag = false;
   end
end
if check_mane_flag
   fprintf("=====深空机动事件检验通过=====\n");
else
   fprintf("=====深空机动事件检验未通过=====\n");
end
%% 检查递推段精度要求
% 检查近地点/近月点高度是否满足约束
[C0,~]=find(events==0);
check_ode_flag = true;
if C0(1)==1
   fprintf("无动力滑翔段状态有误：结果文件的前两行数据应为地球出发状态，不能为无动力滑翔段\n");
   check_ode_flag = false;
end
for i=1:length(C0)
   if C0(i)+1<length(events)
       t0 = times(C0(i)-1,:);
       t1 = times(C0(i),:);
       t2 = times(C0(i)+1,:);
       r0 = rts(C0(i)-1,:);
       r1 = rts(C0(i),:);
       r2 = rts(C0(i)+1,:);
       v0 = vts(C0(i)-1,:);
       v1 = vts(C0(i),:);
       v2 = vts(C0(i)+1,:); 
       M_fuel_0 = M_fuels(C0(i)-1);
       M_fuel_1 = M_fuels(C0(i));
       M_fuel_2 = M_fuels(C0(i)+1);
  
       event0 = events(C0(i)-1);
       if event0~=0
           if norm(t1-t0)>1e-6||norm(r1-r0)>1e-6||norm(v1-v0)>1e-6||norm(M_fuel_1-M_fuel_0)>1e-6
               fprintf("无动力滑翔段状态有误：第%d行数据，从其他事件切换至无动力滑翔段时，切换时刻和航天器的状态应相同\n",C0(i));
               check_ode_flag = false;
           end
       end
  
       event2 = events(C0(i)+1);
       if event2~=0
           continue;
       end
       if norm(t2-t1)<1e-6
           fprintf("无动力滑翔段状态有误：第%d行数据，无动力滑翔时间过短\n",C0(i)+1);
           check_ode_flag = false;
       end
       if C0(i)+2<=length(events)
           event3 = events(C0(i)+2);
      
           s1 = [r1(:);v1(:)];
           [~,Xt] = ode45(@(t,s)Dynamic_CRTBP(t,s,mu), [0,t2-t1], s1, opt);
           r1t = Xt(end,1:2);
           v1t = Xt(end,3:4);
      
           vec_r_earth = Xt(:,1:2);
           vec_r_moon = Xt(:,1:2);
           vec_r_earth(:,1) = vec_r_earth(:,1) - (-mu);
           vec_r_moon(:,1) = vec_r_moon(:,1) - (1-mu);
           r_r_earth = vecnorm(vec_r_earth,2,2);
           r_r_moon = vecnorm(vec_r_moon,2,2);
           d_r_earth = r_r_earth - (6378+400)/LU;
           d_r_moon = r_r_moon - (1737+100)/LU;
      
           if norm(r1t-r2)>1e-6
               fprintf("无动力滑翔段状态有误：第%d行数据，末端位置矢量不满足精度要求，偏差的模为：%.6f\n",C0(i)+1,norm(r1t-r2));
               check_ode_flag = false;
           end
           if norm(v1t-v2)>1e-6
               fprintf("无动力滑翔段状态有误：第%d行数据，末端速度矢量不满足精度要求，偏差的模为：%.6f\n",C0(i)+1,norm(v1t-v2));
               check_ode_flag = false;
           end
           if norm(M_fuel_2-M_fuel_1)>1e-6
               fprintf("无动力滑翔段状态有误：第%d行数据，滑翔段燃料质量不应发生变化\n",C0(i)+1);
               check_ode_flag = false;
           end
           if min(d_r_earth)<-1e-6&&event3~=4
               fprintf("无动力滑翔段状态有误：第%d行数据，滑翔段近地点高度过低，当前为%.1fkm，不能低于400km\n",C0(i),min(r_r_earth)*LU-6378);
               check_ode_flag = false;
           end
           % Octave-compatible findpeaks for negative values
           if  event3==4
               % Avoid depending on the optional `signal` package in unified runs.
               a = local_maxima(-d_r_earth);
               if ~isempty(a)
                   if length(a)==1
                       if min(-a)< -1e-6
                           fprintf("无动力滑翔段状态有误：第%d行数据，滑翔段近地点高度过低，当前为%.1fkm，不能低于400km\n",C0(i),min(-a)*LU+400*LU);
                           check_ode_flag = false;
                       end
                   else
                       if min(-a)<0
                           fprintf("无动力滑翔段状态有误：第%d行数据，滑翔段近地点高度过低，当前为%.1fkm，不能低于400km\n",C0(i),min(-a)*LU);
                           check_ode_flag = false;
                       end
                   end
               end
           end
           if min(d_r_moon)<-1e-6
               fprintf("无动力滑翔段状态有误：第%d行数据，滑翔段近月点高度过低，当前为%.1fkm，不能低于100km\n",C0(i),min(r_r_moon)*LU-1737);
               check_ode_flag = false;
           end
           if max(r_r_earth)>2+1e-6
               fprintf("无动力滑翔段状态有误：第%d行数据，滑翔段远地点过远，当前为%.1f倍地月距离，不能超出2倍地月距离\n",C0(i),max(r_r_earth));
               check_ode_flag = false;
           end
       end
   end
end
if check_ode_flag
   fprintf("=====无动力滑翔段检验通过=====\n");
else
   fprintf("=====无动力滑翔段检验未通过=====\n");
end
%% 检查补给飞船对接约束
[C5,~]=find(events==5);
check_supply_flag = true;
diff_M_fuel = diff(M_fuels);
if ~isempty(C5)
   if mod(length(C5),2)~=0
       fprintf("补给飞船对接状态有误：对接补给飞船的数据应为连续的两行，第一行数据为对接时的状态，第二行数据为燃料补给后的状态，这两行的时刻位置速度可不相同\n");
       check_mane_flag = false;
   end
   [D,~]=find(diff_M_fuel>0);
   for i=1:length(D)
       check_flag = ismember(D(i)+1,C5);
       if ~check_flag
           fprintf("补给飞船对接状态有误：第%d行数据，在非对接状态和深空机动状态发生燃料质量变化\n",D(i)+1);
           check_supply_flag = false;
       end
   end
   for i=1:length(C5)
       t5 = times(C5(i));
       r5 = rts(C5(i),:);
       v5 = vts(C5(i),:);
       [rt,vt] = Get_Phase(s_lyapunov,T_lyapunov,mu,t5);
       if norm(r5-rt)>1e-6
           fprintf("补给飞船对接状态有误：第%d行数据，对接位置矢量不满足精度要求，偏差的模为：%.6f\n",C5(i),norm(r5-rt));
           check_supply_flag = false;
       end
       if norm(v5-vt)>1e-6
           fprintf("补给飞船对接状态有误：第%d行数据，对接速度矢量不满足精度要求，偏差的模为：%.6f\n",C5(i),norm(v5-vt));
           check_supply_flag = false;
       end
   end
end
if check_supply_flag
   fprintf("=====补给飞船状态检验通过=====\n");
else
   fprintf("=====补给飞船状态检验未通过=====\n");
end
%% 检查返回状态是否正确
[C4,~]=find(events==4);
check_return_flag = true;
if length(C4)~=1||C4~=length(events)
   fprintf("返回地球状态有误：事件为4的数据应只有一行，且为最后一行\n");
   check_return_flag = false;
end
if ~isempty(C4)
   t_arr_earth = times(C4);
   r4 = rts(C4,:);
   v4 = vts(C4,:);
   M_fuel_4 = M_fuels(C4);
   r4(1) = r4(1) - (-mu);
   d_r_earth = norm(r4) - 6378/LU;
   cosphi = dot(r4,v4)/norm(r4)/norm(v4);
   if abs(cosphi)>1e-3
       fprintf("返回地球状态有误：返回状态不满足近地点要求\n");
       check_return_flag = false;
   end
   if abs(d_r_earth)>1e-6
       fprintf("返回地球状态有误：近地点高度不满足精度要求，当前高度%.1fkm，精度容差%.1fkm\n",abs(d_r_earth)*LU,1e-6*LU);
       check_return_flag = false;
   end
   if abs(M_fuel_4)>100
       fprintf("返回地球状态有误：返回时携带燃料过多，当前携带%.1fkg，应限制在100kg以内\n",M_fuel_4);
       check_return_flag = false;
   end
end
if check_return_flag
   fprintf("=====返回地球状态检验通过=====\n");
else
   fprintf("=====返回地球状态检验未通过=====\n");
end
%% 打印最终结果
if check_return_flag&&check_supply_flag&&check_ode_flag&&check_mane_flag&&check_C3_flag...
  &&check_events_flag&&check_arr_moon_flag&&check_dep_moon_flag
  
   consume_fuel = diff_M_fuel;
   if ~isempty(C5)
       consume_fuel(C5-1) = 0;
   end
   total_fuel = sum(abs(consume_fuel));
   fprintf("=====结果文件全部检验通过=====\n");
   fprintf("地球出发时刻：%.6f [TU]\n",t_dep_earth);
   fprintf("返回地球时刻：%.6f [TU]\n",t_arr_earth);
   fprintf("任务周期：%.3f day\n",(t_arr_earth - t_dep_earth)*TU/86400);
   fprintf("发射能量：%.6f km^2/s^2\n",C3_energy);
   fprintf("飞船总质量：%.6f kg\n",M0);
   fprintf("初始燃料质量：%.6f kg\n",M_fuel_dep);
   fprintf("飞船运载质量：%.6f kg\n",M_carry_dep);
   fprintf("燃料总消耗质量：%.6f kg\n",total_fuel);
   fprintf("==========================\n");
else
   fprintf("=====结果文件未检验通过=====\n");
end
diary off

end  % end of main function

% Subfunctions
function dM_fuel = Cal_dM_fuel(M0,dv)
   % 这里输入的dv为m/s，M0为kg
   dM_fuel = M0*(1-exp(-dv/3000));
end

function [rt,vt] = Get_Phase(s0,T,mu,t)
% 获取相位tau对应的点的状态信息
% tau：单位deg
% T：轨道周期
   tf = mod(t,T);
   if tf==0
       rt = [s0(1),s0(2)];
       vt = [s0(3),s0(4)];
       return;
   end
   opt=odeset('RelTol', 1e-12, 'AbsTol', 1e-12);
   [~, Xt]=ode45(@(t,s)Dynamic_CRTBP(t,s,mu), [0, tf], s0, opt);
   rt=Xt(end,1:2);
   vt=Xt(end,3:4);
end

function ds=Dynamic_CRTBP(t,s,mu)
% 平面圆型限制性三体问题动力学微分方程
   ds=zeros(4,1);
   x=s(1);
   y=s(2);
   dx=s(3);
   dy=s(4);
   r1=s(1:2) + [mu;0];
   r2=s(1:2) + [mu-1;0];
   ds(1:2)=s(3:4);
   ds(3)=2*dy+x-(1-mu)*(x+mu)/norm(r1)^3-mu*(x-1+mu)/norm(r2)^3;
   ds(4)=-2*dx+y-(1-mu)*y/norm(r1)^3-mu*y/norm(r2)^3;
end

function peaks = local_maxima(values)
peaks = [];
n = length(values);
if n < 3
   return;
end
for idx = 2:(n-1)
   left = values(idx-1);
   center = values(idx);
   right = values(idx+1);
   if (center >= left && center > right) || (center > left && center >= right)
      peaks(end+1,1) = center;
   end
end
end

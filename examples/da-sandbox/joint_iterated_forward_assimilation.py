################################################################################# 
# Copyright (c) 2021, the California Institute of Technology (Caltech).         #
# All rights reserved.                                                          #
#                                                                               #
# Redistribution and use in source and binary forms for academic and other      #
# non-commercial purposes with or without modification, are permitted           #
# provided that the following conditions are met. Commercial users contact      #
# innovation@caltech.edu for a license.                                         #
#                                                                               #
# * Redistributions of source code, including modified source code, must        # 
# retain the above copyright notice, this list of conditions and the            # 
# following disclaimer.                                                         #
#                                                                               #
# * Redistributions in binary form or a modified form of the source code        #
# must reproduce the above copyright notice, this list of conditions and        #
# the following disclaimer in the documentation and/or other materials          #
# provided with the distribution.                                               #
#                                                                               #
# * Neither the name of Caltech, any of its trademarks, the names of its        #
# employees, nor contributors to the source code may be used to endorse or      #
# promote products derived from this software without specific prior            #
# written permission.                                                           #
#                                                                               #
# * Where a modified version of the source code is redistributed publicly       #
# in source or binary forms, the modified source code must be published in      #
# a freely accessible manner, or otherwise redistributed at no charge to        #
# anyone requesting a copy of the modified source code, subject to the same     #
# terms as this agreement.                                                      #
#                                                                               #
# THIS SOFTWARE IS PROVIDED BY CALTECH “AS IS” AND ANY EXPRESS OR IMPLIED       #
# WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF          #
# MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO    #
# EVENT SHALL THE CONTRIBUTORS, CALTECH, ITS FACULTY, STUDENTS, EMPLOYEES, OR   # 
# TRUSTEES BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY,  #
# OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF       #
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS      #
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN       #
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)       #
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE    #
# POSSIBILITY OF SUCH DAMAGE.IMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR      #
# SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER    #
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, # 
# OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE # 
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.          #
#################################################################################

import os, sys; sys.path.append(os.path.join('..', '..'))

from timeit import default_timer as timer
import numpy as np
from scipy import sparse
from matplotlib import pyplot as plt
import copy 

from epiforecast.user_base import FullUserGraphBuilder
from epiforecast.forward_data_assimilator import DataAssimilator
from epiforecast.time_series import EnsembleTimeSeries
from epiforecast.epidemic_data_storage import StaticIntervalDataSeries
from epiforecast.epiplots import (plot_roc_curve, 
                                  plot_ensemble_states, 
                                  plot_epidemic_data,
                                  plot_transmission_rate, 
                                  plot_network_averaged_clinical_parameters,
                                  plot_ensemble_averaged_clinical_parameters)
from epiforecast.utilities import dict_slice, compartments_count
from epiforecast.populations import extract_ensemble_transition_rates, extract_network_transition_rates

# Runs an epidemic with probabilistic master equations alongside one another 
# feedback from epidemic to master equations using an iterated forward sweep data assimilator
# feedback from master equations to epidemic using model based interventions


def get_start_time(start_end_time):
    return start_end_time.start

################################################################################
# initialization ###############################################################
################################################################################

# arguments parsing ############################################################
from _argparse_init import arguments

# constants ####################################################################
from _constants import (static_contact_interval,
                        start_time,
                        end_time,
                        total_time,
                        time_span,
                        distanced_max_contact_rate,
                        OUTPUT_PATH,
                        SEED_JOINT_EPIDEMIC,
                        min_contact_rate,
                        max_contact_rate,
                        age_indep_transition_rates_true,
                        age_dep_transition_rates_true)

# utilities ####################################################################
from _utilities import (print_info,
                        list_of_transition_rates_to_array,
                        modulo_is_close_to_zero,
                        are_close)

# general init #################################################################
import _general_init

# contact network ##############################################################
from _network_init import population, network, populace

# stochastic model #############################################################
from _stochastic_init import (kinetic_ic, 
                              epidemic_simulator)

# user network #################################################################
from _user_network_init import user_network, user_nodes, user_population

age_category_of_users = user_network.get_age_groups() 

np.save(os.path.join(OUTPUT_PATH, 'user_nodes.npy'), 
        user_nodes)

# observations #################################################################
from _observations_init import (sensor_readings,
                                MDT_neighbor_test,
                                MDT_budget_random_test,
                                MDT_result_delay,
                                RDT_budget_random_test,
                                RDT_result_delay,
                                positive_hospital_records,
                                negative_hospital_records,
                                positive_death_records,
                                negative_death_records,
                                data_transform)


sensor_observations = [sensor_readings]

viral_test_observations = [RDT_budget_random_test]
test_result_delay = RDT_result_delay # delay to results of the virus test

#record_observations   = [positive_hospital_records,
#                          positive_death_records]

record_observations   = [positive_hospital_records,
                         negative_hospital_records,
                         positive_death_records,
                         negative_death_records]

if arguments.prior_run:
    sensor_observations = []
    viral_test_observations = []
    record_observations = []
    

# master equations #############################################################
from _master_eqn_init import (master_eqn_ensemble,
                              ensemble_size,
                              ensemble_ic,
                              transition_rates_ensemble,
                              community_transmission_rate_ensemble,
                              learn_transition_rates,
                              learn_transmission_rate,
                              parameter_str,
                              transition_rates_min,
                              transition_rates_max,
                              transmission_rate_min,
                              transmission_rate_max,
                              param_transform,
                              n_forward_steps,
                              n_backward_steps)

# assimilator ##################################################################
transition_rates_to_update_str   = parameter_str
transmission_rate_to_update_flag = learn_transmission_rate 

if arguments.prior_run:
    transition_rates_to_update_str   = []
    transmission_rate_to_update_flag = False
    

sensor_assimilator = DataAssimilator(
        observations=sensor_observations,
        errors=[],
        data_transform=data_transform,
        n_assimilation_batches = arguments.assimilation_batches_sensor,
        transition_rates_to_update_str=[],
        transmission_rate_to_update_flag=False,#transmission_rate_to_update_flag,
        update_type=arguments.assimilation_update_sensor,
        elementwise_reg=arguments.sensor_assimilation_elementwise_regularization,
        joint_cov_noise=arguments.sensor_assimilation_joint_regularization,
        obs_cov_noise=arguments.sensor_assimilation_obs_regularization,
        full_svd=True,
        inflate_states=arguments.assimilation_inflation,
        inflate_reg=arguments.assimilation_sensor_inflation,
        additive_inflate=arguments.assimilation_additive_inflation,
        additive_inflate_factor=arguments.assimilation_additive_inflation_factor,
        inflate_I_only=arguments.assimilation_inflate_I_only,
        distance_threshold=arguments.distance_threshold,        
        transmission_rate_min=transmission_rate_min,
        transmission_rate_max=transmission_rate_max,
        transmission_rate_transform=param_transform,
        transmission_rate_inflation=arguments.params_transmission_inflation,
    mass_conservation_flag = not (arguments.sensor_ignore_mass_constraint),
        output_path=OUTPUT_PATH)

viral_test_assimilator = DataAssimilator(
        observations=viral_test_observations,
        errors=[],
        data_transform=data_transform,
        n_assimilation_batches = arguments.assimilation_batches_test,
        transition_rates_to_update_str=transition_rates_to_update_str,
        transmission_rate_to_update_flag=transmission_rate_to_update_flag,
        update_type=arguments.assimilation_update_test,
        elementwise_reg=arguments.test_assimilation_elementwise_regularization,
        joint_cov_noise=arguments.test_assimilation_joint_regularization,
        obs_cov_noise=arguments.test_assimilation_obs_regularization,
        full_svd=True,
        inflate_states=arguments.assimilation_inflation,
        inflate_reg=arguments.assimilation_test_inflation,
        additive_inflate=arguments.assimilation_additive_inflation,
        additive_inflate_factor=arguments.assimilation_additive_inflation_factor,
        inflate_I_only=arguments.assimilation_inflate_I_only,
        distance_threshold=arguments.distance_threshold,
        transition_rates_min=transition_rates_min,
        transition_rates_max=transition_rates_max,
        transmission_rate_min=transmission_rate_min,
        transmission_rate_max=transmission_rate_max,
        transmission_rate_transform=param_transform,
        transmission_rate_inflation=arguments.params_transmission_inflation,
    mass_conservation_flag = not (arguments.test_ignore_mass_constraint),
        output_path=OUTPUT_PATH)

record_assimilator = DataAssimilator(
        observations=record_observations,
        errors=[],
        data_transform=data_transform,
        HDflag=1,
        n_assimilation_batches=arguments.assimilation_batches_record,
        transition_rates_to_update_str=[],
        transmission_rate_to_update_flag=transmission_rate_to_update_flag,
        update_type=arguments.assimilation_update_record,
        elementwise_reg=arguments.record_assimilation_elementwise_regularization,
        joint_cov_noise=arguments.record_assimilation_joint_regularization,
        obs_cov_noise=arguments.record_assimilation_obs_regularization,
        full_svd=True,    
        inflate_states=arguments.assimilation_inflation,
        inflate_reg=arguments.assimilation_record_inflation,
        additive_inflate=arguments.assimilation_additive_inflation,
        additive_inflate_factor=arguments.assimilation_additive_inflation_factor,
        inflate_I_only=arguments.assimilation_inflate_I_only,
        distance_threshold=arguments.distance_threshold,
        transition_rates_min=transition_rates_min,
        transition_rates_max=transition_rates_max,
        transmission_rate_min=transmission_rate_min,
        transmission_rate_max=transmission_rate_max,
        transmission_rate_transform=param_transform,
        transmission_rate_inflation=arguments.params_transmission_inflation,
    mass_conservation_flag = not (arguments.record_ignore_mass_constraint),
        output_path=OUTPUT_PATH)

# post-processing ##############################################################
#from _post_process_init import axes
fig, axes = plt.subplots(1, 3, figsize = (16, 4))

# inverventions ################################################################
from _intervention_init import (intervention,
                                intervention_frequency,
                                intervention_nodes, 
                                intervention_type,
                                query_intervention,
                                intervention_sick_isolate_time) 

################################################################################
# epidemic setup ###############################################################
################################################################################

from _utilities import print_start_of, print_end_of, print_info_module
################################################################################
kinetic_state = kinetic_ic # dict { node : compartment }

user_state = dict_slice(kinetic_state, user_nodes)
n_S, n_E, n_I, n_H, n_R, n_D = compartments_count(user_state)
statuses_sum_trace = []
statuses_sum_trace.append([n_S, n_E, n_I, n_H, n_R, n_D])

kinetic_states_timeseries = []
kinetic_states_timeseries.append(kinetic_state) # storing ic
  
if user_population < population:
    full_state = dict_slice(kinetic_state, populace)
    n_S, n_E, n_I, n_H, n_R, n_D = compartments_count(full_state)
    full_statuses_sum_trace = []
    full_statuses_sum_trace.append([n_S, n_E, n_I, n_H, n_R, n_D])

  

################################################################################
# master equations + data assimilation init ####################################
################################################################################
# constants ####################################################################

if arguments.prior_run:
    noda_delay=1000.0
else:
    noda_delay=1.0

#floats
da_window         = arguments.assimilation_window
prediction_window = 1.0
save_to_file_interval = 1.0
sensor_assimilation_interval  = 1.0*noda_delay # same for I
test_assimilation_interval  = 1.0*noda_delay # same for I
record_assimilation_interval = 1.0*noda_delay # assimilate H and D data every .. days

intervention_start_time = arguments.intervention_start_time
intervention_interval = arguments.intervention_interval
#ints
n_sweeps                     = arguments.assimilation_sweeps
n_record_sweeps              = 1
n_prediction_windows_spin_up = 8
n_prediction_windows         = int(total_time/prediction_window)
steps_per_da_window          = int(da_window/static_contact_interval)
steps_per_prediction_window  = int(prediction_window/static_contact_interval)

assert n_prediction_windows_spin_up * prediction_window + prediction_window > da_window
earliest_assimilation_time = (n_prediction_windows_spin_up + 1)* prediction_window - da_window 
assert n_prediction_windows > n_prediction_windows_spin_up

spin_up_steps = n_prediction_windows_spin_up * steps_per_prediction_window
prediction_steps = n_prediction_windows * steps_per_prediction_window

# epidemic storage #############################################################
# Set an upper limit on number of stored contact networks:
if intervention_nodes == "contact_tracing": #then we have a history
    steps_per_contact_trace = int(arguments.intervention_contact_trace_days/static_contact_interval)
    max_networks = max(steps_per_da_window + steps_per_prediction_window, steps_per_contact_trace)
else:
    max_networks = steps_per_da_window + steps_per_prediction_window 

epidemic_data_storage = StaticIntervalDataSeries(static_contact_interval, max_networks=max_networks)

# storing ######################################################################
#for the initial run we smooth over a window, store data by time-stamp.
ensemble_state_series_dict = {} 

master_states_sum_timeseries  = EnsembleTimeSeries(ensemble_size,
                                                   6,
                                                   time_span.size)

#to store the ensemble of the mean over the network of the parameters
mean_transmission_rate_timeseries = EnsembleTimeSeries(ensemble_size,
                                                       1,
                                                       time_span.size)
if param_transform == 'log':
    mean_logtransmission_rate_timeseries = EnsembleTimeSeries(ensemble_size,
                                                              1,
                                                              time_span.size)


mean_transition_rates_timeseries = EnsembleTimeSeries(ensemble_size,
                                              6,
                                              time_span.size)


#to store the network parameters of the mean over the ensemble
network_transmission_rate_timeseries = EnsembleTimeSeries(1,
                                                          user_population,
                                                          time_span.size)

network_transition_rates_timeseries = EnsembleTimeSeries(6,
                                                        user_population,
                                                        time_span.size)

# intial conditions  ###########################################################

master_eqn_ensemble.set_states_ensemble(ensemble_ic)
master_eqn_ensemble.set_start_time(start_time)

################################################################################
# master equations + data assimilation computation #############################
################################################################################
# spin-up w/o data assimilation ################################################
current_time = start_time
ensemble_state = ensemble_ic

timer_spin_up = timer()

print_info("Spin-up started")
for j in range(spin_up_steps):
    walltime_master_eqn = 0.0
    master_eqn_ensemble.reset_walltimes()
    #Run kinetic model
    # run
    KE_timer = timer()
    network = epidemic_simulator.run(
            stop_time=current_time + static_contact_interval,
            current_network=network)
    print("KE runtime", timer()-KE_timer, flush=True)
    # store for further usage (master equations etc)
    DS_timer = timer()
    epidemic_data_storage.save_network_by_start_time(
            start_time=current_time,
            contact_network=network)
    epidemic_data_storage.save_start_statuses_to_network(
            start_time=current_time,
            start_statuses=kinetic_state)
    
    # save kinetic data if required, note current time has advanced since saving ensemble state:
    save_kinetic_state_now = modulo_is_close_to_zero(current_time, 
                                                     save_to_file_interval, 
                                                     eps=static_contact_interval)
    if save_kinetic_state_now:
        kinetic_state_path = os.path.join(OUTPUT_PATH, 'kinetic_eqns_statuses_at_step_'+str(j)+'.npy')
        kinetic_eqns_statuses = dict_slice(kinetic_state, user_nodes)
        np.save(kinetic_state_path, kinetic_eqns_statuses)
        if user_population < population:
            full_kinetic_state_path = os.path.join(OUTPUT_PATH, 'full_kinetic_eqns_statuses_at_step_'+str(j)+'.npy')
            full_kinetic_eqns_statuses = dict_slice(kinetic_state, populace)
            np.save(full_kinetic_state_path, full_kinetic_eqns_statuses)
        
        
            
    kinetic_state = epidemic_simulator.kinetic_model.current_statuses
    epidemic_data_storage.save_end_statuses_to_network(
            end_time=current_time+static_contact_interval,
            end_statuses=kinetic_state)
    print("network and data storage runtime",timer()-DS_timer,flush=True) 
    # store for plotting
    PS_timer = timer() 
    user_state = dict_slice(kinetic_state, user_nodes)
    n_S, n_E, n_I, n_H, n_R, n_D = compartments_count(user_state)
    statuses_sum_trace.append([n_S, n_E, n_I, n_H, n_R, n_D])
    
    if user_population < population:
        full_state = dict_slice(kinetic_state, populace)
        n_S, n_E, n_I, n_H, n_R, n_D = compartments_count(full_state)
        full_statuses_sum_trace.append([n_S, n_E, n_I, n_H, n_R, n_D])


    kinetic_states_timeseries.append(kinetic_state)
    print("store KE statuses and timeseries runtime", timer() - PS_timer,flush=True)
    
    
  

    # now for the master eqn
    ensemble_state_frac = ensemble_state.reshape(ensemble_size, 6, -1).sum(axis = 2)/user_population
    master_states_sum_timeseries.push_back(ensemble_state_frac) # storage
    
    if learn_transmission_rate == True:
        mean_community_transmission_rate_ensemble = community_transmission_rate_ensemble.mean(axis=1)[:,np.newaxis]
        mean_transmission_rate_timeseries.push_back(
                mean_community_transmission_rate_ensemble)
        if param_transform == 'log':
            mean_community_logtransmission_rate_ensemble = np.log(community_transmission_rate_ensemble).mean(axis=1)[:,np.newaxis]
            mean_logtransmission_rate_timeseries.push_back(mean_community_logtransmission_rate_ensemble)

        community_transmission_rate_means = community_transmission_rate_ensemble.mean(axis=0)[np.newaxis,:] #here we avereage the ensemble!
        network_transmission_rate_timeseries.push_back(
                community_transmission_rate_means)
        
    if learn_transition_rates == True:
        mean_transition_rates_timeseries.push_back(
                extract_ensemble_transition_rates(transition_rates_ensemble))
        network_transition_rates_timeseries.push_back(
            extract_network_transition_rates(transition_rates_ensemble, user_population))
        

    #save the ensemble if required - we do here are we do not save master eqn at end of DA-windows
    save_ensemble_state_now = modulo_is_close_to_zero(current_time - static_contact_interval, 
                                                      save_to_file_interval, 
                                                      eps=static_contact_interval)
    if save_ensemble_state_now:
        ensemble_state_path = os.path.join(OUTPUT_PATH, 'master_eqns_mean_states_at_step_'+str(j-1)+'.npy')
        master_eqns_mean_states = ensemble_state.mean(axis=0)
        np.save(ensemble_state_path,master_eqns_mean_states)
            
    loaded_data = epidemic_data_storage.get_network_from_start_time(
            start_time=current_time)

    
    user_network.update_from(loaded_data.contact_network)
    
    # For the purpose of generating a plot of contacts, save the spin up contact matrices every 3 hours
    mean_contact_durations_path = os.path.join(OUTPUT_PATH,'user_mean_contact_durations_sparse_at_step_'+str(j)+'.npz')
    sparse.save_npz(mean_contact_durations_path,user_network.get_edge_weights())

    master_eqn_ensemble.set_mean_contact_duration(
            user_network.get_edge_weights())
    master_eqn_ensemble.set_diurnally_averaged_nodal_activation_rate(
        user_network.get_lambda_integrated())

    timer_master_eqn = timer()
    

    ensemble_state = master_eqn_ensemble.simulate(
        static_contact_interval,
        min_steps=n_forward_steps)
    #move to new time
    current_time += static_contact_interval
    current_time_span = [time for time in time_span if time < current_time+static_contact_interval]
    walltime_master_eqn += timer() - timer_master_eqn
    print_info("eval_closure walltime:", master_eqn_ensemble.get_walltime_eval_closure())
    print_info("master equations walltime:", walltime_master_eqn, end='\n\n')

    #in theory should do nothing
    master_eqn_ensemble.set_states_ensemble(ensemble_state)
    master_eqn_ensemble.set_start_time(current_time)

    #generate data to be assimilated later on
    if current_time > (earliest_assimilation_time - 0.1*static_contact_interval):
        observe_sensor_now = modulo_is_close_to_zero(current_time,
                                                   sensor_assimilation_interval,
                                                   eps=static_contact_interval)
        if observe_sensor_now:
            sensor_assimilator.find_and_store_observations(
                ensemble_state,
                loaded_data.end_statuses,
                user_network,
                current_time)
            

        observe_test_now = modulo_is_close_to_zero(current_time,
                                                   test_assimilation_interval,
                                                   eps=static_contact_interval)
        if observe_test_now:
            viral_test_assimilator.find_and_store_observations(
                ensemble_state,
                loaded_data.end_statuses,
                user_network,
                current_time)

        observe_record_now = modulo_is_close_to_zero(current_time,
                                                    record_assimilation_interval,
                                                    eps=static_contact_interval)
        if observe_record_now:
            record_assimilator.find_and_store_observations(
                ensemble_state,
                loaded_data.end_statuses,
                user_network,
                current_time)

        if observe_sensor_now or observe_test_now or observe_record_now:
            ensemble_state_series_dict[current_time] = copy.deepcopy(ensemble_state )


    #plots on the fly
    plot_and_save_now = modulo_is_close_to_zero(current_time - static_contact_interval, 
                                                save_to_file_interval, 
                                                eps=static_contact_interval)
    if plot_and_save_now:
        if (current_time - static_contact_interval) > static_contact_interval: # i.e not first step
            plt.close(fig)

            if learn_transmission_rate == True:
                plot_transmission_rate(mean_transmission_rate_timeseries.container[:,:, :len(current_time_span)-1],
                                       current_time_span[:-1],
                                       a_min=0.0,
                                       output_path=OUTPUT_PATH)
                if param_transform == 'log':
                    plot_transmission_rate(mean_logtransmission_rate_timeseries.container[:,:, :len(current_time_span)-1],
                                           current_time_span[:-1],
                                           a_min=0.0,
                                           output_path=OUTPUT_PATH,
                                           output_name='logtransmission_rate')

                plot_transmission_rate(np.swapaxes(network_transmission_rate_timeseries.container[:,:, :len(current_time_span)-1], 0, 1),
                                       current_time_span[:-1],
                                       a_min=0.0,
                                       output_path=OUTPUT_PATH,
                                       output_name='networktransmission_rate')
            
            if learn_transition_rates == True:
                
                plot_network_averaged_clinical_parameters(
                    mean_transition_rates_timeseries.container[:,:,:len(current_time_span)-1],
                    current_time_span[:-1],
                    age_category_of_users,
                    age_indep_rates_true = age_indep_transition_rates_true,
                    age_dep_rates_true = age_dep_transition_rates_true,
                    a_min=0.0,
                    output_path=OUTPUT_PATH,
                    output_name='mean')
                plot_ensemble_averaged_clinical_parameters(
                    np.swapaxes(network_transition_rates_timeseries.container[:,:,:len(current_time_span)-1], 0, 1),
                    current_time_span[:-1],
                    age_category_of_users,
                    age_indep_rates_true = age_indep_transition_rates_true,
                    age_dep_rates_true = age_dep_transition_rates_true,
                    a_min=0.0,
                    output_path=OUTPUT_PATH,
                    output_name='network')
                
            fig, axes = plt.subplots(1, 3, figsize = (16, 4))
            axes = plot_epidemic_data(user_population, 
                                      statuses_sum_trace, 
                                      axes, 
                                      current_time_span)
    
            plt.savefig(os.path.join(OUTPUT_PATH, 'epidemic.png'), rasterized=True, dpi=150)
            
            axes = plot_ensemble_states(user_population,
                                        population,
                                        master_states_sum_timeseries.container[:,:, :len(current_time_span)-1],
                                        current_time_span[:-1],
                                        axes=axes,
                                        xlims=(-0.1, current_time),
                                        a_min=0.0)
            plt.savefig(os.path.join(OUTPUT_PATH, 'epidemic_and_master_eqn.png'),
                        rasterized=True,
                        dpi=150)


    #intervention if required
    intervene_now = query_intervention(intervention_frequency,current_time,intervention_start_time, static_contact_interval)    
    
    if intervene_now:
        
        # now see which nodes have intervention applied
        if intervention_nodes == "all":
            nodes_to_intervene = network.get_nodes()
            print("intervention applied to all {:d} nodes.".format(
                network.get_node_count()))
        
        elif intervention_nodes == "sick":
            #returns full network nodes to intervene 
            nodes_to_intervene_current = intervention.find_sick(ensemble_state, user_nodes, sum_EI=arguments.intervention_sum_EI)
            intervention.save_nodes_to_intervene(current_time, 
                                                 nodes_to_intervene_current)
            nodes_to_intervene = \
                    np.unique( \
                    np.concatenate([v \
                    for k, v in intervention.stored_nodes_to_intervene.items() \
                    if k > current_time - intervention_sick_isolate_time]) \
                    )

        elif intervention_nodes == "random":
            if current_time % intervention_sick_isolate_time == \
               intervention_start_time % intervention_sick_isolate_time:
                nodes_to_intervene_current = np.random.choice(network.get_nodes(),\
                                       arguments.intervention_random_isolate_budget,\
                                       replace=False) 
                intervention.save_nodes_to_intervene(current_time, 
                                                     nodes_to_intervene_current)
            else:
                intervention.save_nodes_to_intervene(current_time,
                             intervention.stored_nodes_to_intervene[current_time-1.0])
            nodes_to_intervene = intervention.stored_nodes_to_intervene[current_time]
           
        elif intervention_nodes == "test_data_only":
            #naively infer PPV or FOR from the test output
            current_positive_nodes = viral_test_assimilator.stored_positively_tested_nodes[current_time]
            intervention.save_nodes_to_intervene(current_time, current_positive_nodes)
            n_intervention_nodes =  np.sum([len(v) for k, v in intervention.stored_nodes_to_intervene.items() 
                                            if k > current_time - intervention_sick_isolate_time])
            if (n_intervention_nodes>0):
                nodes_to_intervene = np.unique(np.concatenate([v for k, v in intervention.stored_nodes_to_intervene.items() \
                                                               if k > current_time - intervention_sick_isolate_time]) )
            else:
                nodes_to_intervene = np.array([],dtype=int)

        elif intervention_nodes == "contact_tracing":
            current_positive_nodes = viral_test_assimilator.stored_positively_tested_nodes[current_time].tolist()
            neighbors_of_positive_nodes = {node : list(user_network.get_graph().neighbors(node)) for node in current_positive_nodes}
            #now we need to check through history, at the duration of contacts
            fifteen_mins = 1.0 / 24.0 / 4.0 
            neighbors_with_long_contact = copy.deepcopy(current_positive_nodes)
            for step in np.arange(steps_per_contact_trace):
                trace_time = current_time - (steps_per_contact_trace - step) * static_contact_interval 
                if trace_time >= 0.0:
                    loaded_data = epidemic_data_storage.get_network_from_start_time(start_time=trace_time)
                    mean_contact_duration = loaded_data.contact_network.get_edge_weights() #weighted sparse adjacency matrix
                    neighbors_with_long_contact_at_trace_time = []
                    for node in current_positive_nodes:
                        mean_contact_with_node = mean_contact_duration[node,:] 
                        long_contact_list = [idx for (i,idx) in enumerate(mean_contact_with_node.indices) if mean_contact_with_node.data[i] > fifteen_mins]
                        neighbors_with_long_contact_at_trace_time.extend(long_contact_list)

                    neighbors_with_long_contact.extend(neighbors_with_long_contact_at_trace_time)

            #now save them and get all the nodes
            neighbors_with_long_contact = np.unique(neighbors_with_long_contact)
            intervention.save_nodes_to_intervene(current_time, neighbors_with_long_contact)
            n_intervention_nodes =  np.sum([len(v) for k, v in intervention.stored_nodes_to_intervene.items() 
                                            if k > current_time - intervention_sick_isolate_time])
            if (n_intervention_nodes>0):
                nodes_to_intervene = np.unique(np.concatenate([v for k, v in intervention.stored_nodes_to_intervene.items() \
                                                               if k > current_time - intervention_sick_isolate_time]) \
                                           )
            else:
                nodes_to_intervene = np.array([],dtype=int)


        else:
            raise ValueError("unknown 'intervention_nodes', choose from 'all' (default), 'sick', 'random', or 'test_data_only'")
            
        print("intervention applied to sick nodes: {:d}/{:d}".format(
            nodes_to_intervene.size, network.get_node_count()))

        # Apply the the chosen form of intervention
        if intervention_type == "isolate":
            network.set_lambdas(min_contact_rate, max_contact_rate)
            if nodes_to_intervene.size>0:
                network.isolate(nodes_to_intervene, 
                                λ_isolation=arguments.intervention_isolate_node_lambda) 
            
            np.save(os.path.join(OUTPUT_PATH, 'isolated_nodes.npy'),
                    intervention.stored_nodes_to_intervene)
        
        elif intervention_type == "social_distance":
            λ_min, λ_max = network.get_lambdas() #returns np.array (num_nodes,) for each lambda [Not a dict!]
            λ_max[:] = distanced_max_contact_rate 
            network.set_lambdas(λ_min,λ_max)

            λ_min, λ_max = user_network.get_lambdas() #returns np.aray( num_nodes,) [ not a dict!]
            λ_max[:] = distanced_max_contact_rate 
            user_network.set_lambdas(λ_min,λ_max)
        elif intervention_type == "nothing":
            np.save(os.path.join(OUTPUT_PATH, 'positive_nodes.npy'),
                    intervention.stored_nodes_to_intervene)

        else:
            raise ValueError("unknown intervention type, choose from 'social_distance' (default), 'isolate' ")

    
        
print_info("Spin-up ended; elapsed:", timer() - timer_spin_up, end='\n\n')
print_info("Spin-up ended: current time", current_time)

# main loop: backward/forward/data assimilation ################################
# 3 stages per loop:
# 1a) run epidemic for the duration of the prediction window 
# 1b) prediction (no assimilation) forwards steps_per_prediction_window
#    - Save data during this window from [ start , end ]
#    - Make observations and store them in the assimilator
# 3) Assimilation update at start of window, using recorded data over the window [start,end]
#    - rerun master equations over window
#    - possibly repeat 3) over n_sweeps
# Repeat from 1)
#

for k in range(n_prediction_windows_spin_up, n_prediction_windows):
    print_info("Prediction window: {}/{}".format(k+1, n_prediction_windows))
    timer_window = timer()
    walltime_master_eqn = 0.0
    walltime_DA_update = 0.0
    master_eqn_ensemble.reset_walltimes()

    assert are_close(current_time,
                     k * prediction_window,
                     eps=static_contact_interval)
    current_time = k * prediction_window # to avoid build-up of errors

    ensemble_state_frac = ensemble_state.reshape(ensemble_size, 6, -1).sum(axis = 2)/user_population
    print(current_time, ensemble_state_frac.mean(axis=0))
    
    ## 1a) Run epidemic simulator
    ## 1b) forward run w/o data assimilation; prediction
    print("Start time = ", current_time, flush=True)
    master_eqn_ensemble.set_start_time(current_time)
    for j in range(steps_per_prediction_window):
                
        # run epidemic_simulator
        network = epidemic_simulator.run(
            stop_time=current_time + static_contact_interval,
            current_network=network)

        # store for further usage (master equations etc)
        epidemic_data_storage.save_network_by_start_time(
            start_time=current_time,
            contact_network=network)
        epidemic_data_storage.save_start_statuses_to_network(
            start_time=current_time,
            start_statuses=kinetic_state)

        # save kinetic data if required:
        save_kinetic_state_now = modulo_is_close_to_zero(current_time, 
                                                         save_to_file_interval,                                                     
                                                         eps=static_contact_interval)
        if save_kinetic_state_now:
            kinetic_state_path = os.path.join(OUTPUT_PATH, 'kinetic_eqns_statuses_at_step_'+str(k*steps_per_prediction_window+j)+'.npy')
            kinetic_eqns_statuses = dict_slice(kinetic_state, user_nodes)
            np.save(kinetic_state_path, kinetic_eqns_statuses)
            if user_population < population:
                full_kinetic_state_path = os.path.join(OUTPUT_PATH, 'full_kinetic_eqns_statuses_at_step_'+str(k*steps_per_prediction_window+j)+'.npy')
                full_kinetic_eqns_statuses = dict_slice(kinetic_state, populace)
                np.save(full_kinetic_state_path, full_kinetic_eqns_statuses)


        kinetic_state = epidemic_simulator.kinetic_model.current_statuses
        epidemic_data_storage.save_end_statuses_to_network(
            end_time=current_time+static_contact_interval,
            end_statuses=kinetic_state)

        # store for plotting
        user_state = dict_slice(kinetic_state, user_nodes)
        n_S, n_E, n_I, n_H, n_R, n_D = compartments_count(user_state)
        statuses_sum_trace.append([n_S, n_E, n_I, n_H, n_R, n_D])
        if user_population < population:
            full_state = dict_slice(kinetic_state, populace)
            n_S, n_E, n_I, n_H, n_R, n_D = compartments_count(full_state)
            full_statuses_sum_trace.append([n_S, n_E, n_I, n_H, n_R, n_D])


        kinetic_states_timeseries.append(kinetic_state)

        # storage of data first (we do not store end of prediction window)
        ensemble_state_frac = ensemble_state.reshape(ensemble_size, 6, -1).sum(axis = 2)/user_population
        master_states_sum_timeseries.push_back(ensemble_state_frac) # storage

        if learn_transmission_rate == True:
            mean_community_transmission_rate_ensemble = community_transmission_rate_ensemble.mean(axis=1)[:,np.newaxis]
            mean_transmission_rate_timeseries.push_back(
                    mean_community_transmission_rate_ensemble)
            if param_transform == 'log':
                mean_community_logtransmission_rate_ensemble = np.log(community_transmission_rate_ensemble).mean(axis=1)[:,np.newaxis]
                mean_logtransmission_rate_timeseries.push_back(
                    mean_community_logtransmission_rate_ensemble)

            community_transmission_rate_means = community_transmission_rate_ensemble.mean(axis=0)[np.newaxis,:] #here we avereage the ensemble!
            network_transmission_rate_timeseries.push_back(
                community_transmission_rate_means)

        if learn_transition_rates == True:
            mean_transition_rates_timeseries.push_back(
                extract_ensemble_transition_rates(transition_rates_ensemble))
            network_transition_rates_timeseries.push_back(
                extract_network_transition_rates(transition_rates_ensemble, user_population))
            
        #save the ensemble if required - we do here are we do not save master eqn at end of DA-windows
        save_ensemble_state_now = modulo_is_close_to_zero(current_time - static_contact_interval, 
                                                          save_to_file_interval, 
                                                          eps=static_contact_interval)
        if save_ensemble_state_now:
            ensemble_state_path = os.path.join(OUTPUT_PATH, 'master_eqns_mean_states_at_step_'+str(k*steps_per_prediction_window+j-1)+'.npy')
            master_eqns_mean_states = ensemble_state.mean(axis=0)
            np.save(ensemble_state_path,master_eqns_mean_states)
                
        loaded_data = epidemic_data_storage.get_network_from_start_time(start_time=current_time)

        user_network.update_from(loaded_data.contact_network)
        master_eqn_ensemble.set_mean_contact_duration(user_network.get_edge_weights())
        master_eqn_ensemble.set_diurnally_averaged_nodal_activation_rate(
            user_network.get_lambda_integrated())

        # run ensemble forward
        timer_master_eqn = timer()
        
        ensemble_state = master_eqn_ensemble.simulate(static_contact_interval,
                                                      min_steps=n_forward_steps)

        walltime_master_eqn += timer() - timer_master_eqn

        current_time += static_contact_interval
        current_time_span = [time for time in time_span if time < current_time+static_contact_interval]
   
        # collect data for later assimilation
        observe_sensor_now = modulo_is_close_to_zero(current_time,
                                                     sensor_assimilation_interval,
                                                     eps=static_contact_interval)

        if observe_sensor_now:
            sensor_assimilator.find_and_store_observations(
                ensemble_state,
                loaded_data.end_statuses,
                user_network,
                current_time)

        observe_test_now = modulo_is_close_to_zero(current_time,
                                                   test_assimilation_interval,
                                                   eps=static_contact_interval)
        if observe_test_now:
            viral_test_assimilator.find_and_store_observations(
                ensemble_state,
                loaded_data.end_statuses,
                user_network,
                current_time)

        observe_record_now = modulo_is_close_to_zero(current_time,
                                                    record_assimilation_interval,
                                                    eps=static_contact_interval)
        if observe_record_now:
            record_assimilator.find_and_store_observations(
                ensemble_state,
                loaded_data.end_statuses,
                user_network,
                current_time)
        
        if observe_sensor_now or observe_test_now or observe_record_now:
            ensemble_state_series_dict[current_time] = copy.deepcopy(ensemble_state)


        #plots on the fly    
        plot_and_save_now = modulo_is_close_to_zero(current_time - static_contact_interval, 
                                                    save_to_file_interval, 
                                                    eps=static_contact_interval)
        if plot_and_save_now:
            plt.close(fig)
            
            if learn_transmission_rate == True:
                plot_transmission_rate(mean_transmission_rate_timeseries.container[:,:, :len(current_time_span)-1],
                                       current_time_span[:-1],
                                       a_min=0.0,
                                       output_path=OUTPUT_PATH)
                if param_transform == 'log':
                    plot_transmission_rate(mean_logtransmission_rate_timeseries.container[:,:, :len(current_time_span)-1],
                                           current_time_span[:-1],
                                           a_min=0.0,
                                           output_path=OUTPUT_PATH,
                                           output_name='logtransmission_rate')

                plot_transmission_rate(np.swapaxes(network_transmission_rate_timeseries.container[:,:, :len(current_time_span)-1],0,1),
                                       current_time_span[:-1],
                                       a_min=0.0,
                                       output_path=OUTPUT_PATH,
                                       output_name='networktransmission_rate')
            
            if learn_transition_rates == True:                
                plot_network_averaged_clinical_parameters(
                    mean_transition_rates_timeseries.container[:,:,:len(current_time_span)-1],
                    current_time_span[:-1],
                    age_category_of_users,
                    age_indep_rates_true = age_indep_transition_rates_true,
                    age_dep_rates_true = age_dep_transition_rates_true,
                    a_min=0.0,
                    output_path=OUTPUT_PATH,
                    output_name='mean')
                plot_ensemble_averaged_clinical_parameters(
                    np.swapaxes(network_transition_rates_timeseries.container[:,:,:len(current_time_span)-1], 0, 1),
                    current_time_span[:-1],
                    age_category_of_users,
                    age_indep_rates_true = age_indep_transition_rates_true,
                    age_dep_rates_true = age_dep_transition_rates_true,
                    a_min=0.0,
                    output_path=OUTPUT_PATH,
                    output_name='network')
            
            fig, axes = plt.subplots(1, 3, figsize = (16, 4))
            axes = plot_epidemic_data(user_population, 
                                      statuses_sum_trace, 
                                      axes, 
                                      current_time_span)
            plt.savefig(os.path.join(OUTPUT_PATH, 'epidemic.png'), rasterized=True, dpi=150)
            

            # plot trajectories
            axes = plot_ensemble_states(user_population,
                                        population,
                                        master_states_sum_timeseries.container[:,:, :len(current_time_span)-1],
                                        current_time_span[:-1],
                                        axes=axes,
                                        xlims=(-0.1, current_time),
                                        a_min=0.0)
            plt.savefig(os.path.join(OUTPUT_PATH, 'epidemic_and_master_eqn.png'),
                        rasterized=True,
                        dpi=150)
            
            
    print_info("Prediction ended: current time:", current_time)
    for step in range((2+n_record_sweeps)*n_sweeps):
         # by restarting from time of first assimilation data
        past_time = current_time - steps_per_da_window * static_contact_interval
    
        if step == 0:
            # remove the earliest dictionaries
            stored_states_times = ensemble_state_series_dict.keys() 
            times_for_removal = [time for time in stored_states_times if time < past_time]
            [ensemble_state_series_dict.pop(time) for time in times_for_removal]
        
        DA_update_timer = timer()
        # DA update of initial state IC and parameters at t0, due to data collected in window [t0,t1]
        non_model_based_interventions = ["test_data_only", "random", "contact_tracing"]
        if intervention_nodes in non_model_based_interventions: #we do no DA updates (though still test the population)
            update_flag=False
            print("no assimilation performed",flush=True)
        else:
            if step % (2+n_record_sweeps) == 0:
                (ensemble_state_series_dict, 
                 transition_rates_ensemble,
                 community_transmission_rate_ensemble,
                 update_flag
             ) = sensor_assimilator.update_initial_from_series(
                 ensemble_state_series_dict, 
                 transition_rates_ensemble,
                 community_transmission_rate_ensemble,
                user_network)       
                print("assimilated sensors",flush=True)
            elif step % (2+n_record_sweeps) == 1:
                (ensemble_state_series_dict, 
                 transition_rates_ensemble,
                 community_transmission_rate_ensemble,
                 update_flag
             ) = viral_test_assimilator.update_initial_from_series(
                 ensemble_state_series_dict, 
                 transition_rates_ensemble,
                 community_transmission_rate_ensemble,
                 user_network)
                
                print("assimilated viral tests",flush=True)
            elif step % (2+n_record_sweeps) >= 2:
                (ensemble_state_series_dict, 
                 transition_rates_ensemble,
                 community_transmission_rate_ensemble,
                 update_flag
             ) = record_assimilator.update_initial_from_series(
                 ensemble_state_series_dict, 
                 transition_rates_ensemble,
                 community_transmission_rate_ensemble,
                 user_network)
                
                print("assimilated records",flush=True)
            
        # run ensemble of master equations again over the da windowprediction loop again without data collection
        walltime_DA_update += timer() - DA_update_timer
    
        if update_flag:
            # update with the new initial state and parameters 
            master_eqn_ensemble.set_states_ensemble(ensemble_state_series_dict[past_time])
            master_eqn_ensemble.set_start_time(past_time)
            master_eqn_ensemble.update_ensemble(
                new_transition_rates=transition_rates_ensemble,
                new_transmission_rate_parameters=community_transmission_rate_ensemble)
            
            ensemble_state_frac = ensemble_state_series_dict[past_time].reshape(ensemble_size, 6, -1).sum(axis = 2)/user_population
#            print(past_time, np.var(ensemble_state[:,982:2*982], axis=0))
                    
            for j in range(steps_per_da_window):
                walltime_master_eqn = 0.0
                master_eqn_ensemble.reset_walltimes()
                # load the new network
                loaded_data = epidemic_data_storage.get_network_from_start_time(
                    start_time=past_time)
                
                user_network.update_from(loaded_data.contact_network)
                master_eqn_ensemble.set_mean_contact_duration(
                    user_network.get_edge_weights())
                master_eqn_ensemble.set_diurnally_averaged_nodal_activation_rate(
                    user_network.get_lambda_integrated())

                timer_master_eqn = timer()
                
                # simulate the master equations
                ensemble_state = master_eqn_ensemble.simulate(
                    static_contact_interval,
                    min_steps=n_forward_steps)
                
                # move to new time
                past_time += static_contact_interval
                walltime_master_eqn += timer() - timer_master_eqn
         
                # overwrite the data.
                observe_sensor_now = modulo_is_close_to_zero(past_time,
                                                             sensor_assimilation_interval,
                                                             eps=static_contact_interval)
                
                observe_test_now = modulo_is_close_to_zero(past_time,
                                                           test_assimilation_interval,
                                                           eps=static_contact_interval)
                
                observe_record_now = modulo_is_close_to_zero(past_time,
                                                             record_assimilation_interval,
                                                             eps=static_contact_interval)
                
                if observe_sensor_now or observe_test_now or observe_record_now:
                    ensemble_state_series_dict[past_time] =copy.deepcopy( ensemble_state )
                
            print("Completed forward sweep iteration {}/{}".format(step + 1, 3*n_sweeps), 
                  " over the interval [{},{}]".format(current_time - steps_per_da_window * static_contact_interval, past_time)) 
            # DA should get back to the current time
            assert are_close(past_time, current_time, eps=static_contact_interval)


        else:
            print("Completed forward sweep iteration {}/{}".format(step+1,3*n_sweeps), ", no forward sweep required")
        

    print_info("Prediction window: {}/{}".format(k+1, n_prediction_windows),
               "ended; elapsed:",
               timer() - timer_window)
    
    print_info("Prediction window: {}/{};".format(k+1, n_prediction_windows),
               "eval_closure walltime:",
               master_eqn_ensemble.get_walltime_eval_closure())
            
    print_info("Prediction window: {}/{};".format(k+1, n_prediction_windows),
               "master equations walltime:",
               walltime_master_eqn, end='\n\n')
    
    print_info("Prediction window: {}/{};".format(k+1, n_prediction_windows),
               "assimilator(s) walltime:",
               walltime_DA_update, end='\n\n')
            
    #4) Intervention
    intervene_now = query_intervention(intervention_frequency,current_time,intervention_start_time, static_contact_interval)    
    
    if intervene_now:
        # now see which nodes have intervention applied
        if intervention_nodes == "all":
            nodes_to_intervene = network.get_nodes() 
            print("intervention applied to all {:d} nodes".format(
                network.get_node_count()))
            
        elif intervention_nodes == "sick":
            #returns full network nodes to intervene 
            nodes_to_intervene_current = intervention.find_sick(ensemble_state, user_nodes, sum_EI=arguments.intervention_sum_EI)
            intervention.save_nodes_to_intervene(current_time, 
                                                 nodes_to_intervene_current)
            nodes_to_intervene = \
                    np.unique( \
                    np.concatenate([v \
                    for k, v in intervention.stored_nodes_to_intervene.items() \
                    if k > current_time - intervention_sick_isolate_time]) \
                    )

        elif intervention_nodes == "random":
            if current_time % intervention_sick_isolate_time == \
               intervention_start_time % intervention_sick_isolate_time:
                nodes_to_intervene_current = np.random.choice(network.get_nodes(),\
                                       arguments.intervention_random_isolate_budget,\
                                       replace=False) 
                intervention.save_nodes_to_intervene(current_time, 
                                                     nodes_to_intervene_current)
            else:
                intervention.save_nodes_to_intervene(current_time,
                             intervention.stored_nodes_to_intervene[current_time-1.0])
            nodes_to_intervene = intervention.stored_nodes_to_intervene[current_time]
            
        elif intervention_nodes == "test_data_only":
            current_positive_nodes = viral_test_assimilator.stored_positively_tested_nodes[current_time]
            intervention.save_nodes_to_intervene(current_time, current_positive_nodes)
            n_intervention_nodes =  np.sum([len(v) for k, v in intervention.stored_nodes_to_intervene.items() 
                                            if k > current_time - intervention_sick_isolate_time])
            if (n_intervention_nodes>0):
                nodes_to_intervene = np.unique(np.concatenate([v for k, v in intervention.stored_nodes_to_intervene.items() \
                                                               if k > current_time - intervention_sick_isolate_time]) \
                                           )
            else:
                nodes_to_intervene = np.array([],dtype=int)
                
        elif intervention_nodes == "contact_tracing":
            #we check the history of contacts with current positive nodes 
            current_positive_nodes = viral_test_assimilator.stored_positively_tested_nodes[current_time].tolist()
            neighbors_of_positive_nodes = {node : list(user_network.get_graph().neighbors(node)) for node in current_positive_nodes}
            #now we need to check through history, at the duration of contacts
            fifteen_mins = 1.0 / 24.0 / 4.0 
            neighbors_with_long_contact = copy.deepcopy(current_positive_nodes)
                    
            for step in np.arange(steps_per_contact_trace):
                trace_time = current_time - (steps_per_contact_trace - step) * static_contact_interval 
                if trace_time >= 0.0:
                    loaded_data = epidemic_data_storage.get_network_from_start_time(start_time=trace_time)
                    mean_contact_duration = loaded_data.contact_network.get_edge_weights() #weighted sparse adjacency matrix
                    neighbors_with_long_contact_at_trace_time = []
                    for node in current_positive_nodes:
                        mean_contact_with_node = mean_contact_duration[node,:] 
                        long_contact_list = [idx for (i,idx) in enumerate(mean_contact_with_node.indices) if mean_contact_with_node.data[i] > fifteen_mins]
                        neighbors_with_long_contact_at_trace_time.extend(long_contact_list)

                       
                    neighbors_with_long_contact.extend(neighbors_with_long_contact_at_trace_time)

            #now save them and get all the nodes
            neighbors_with_long_contact = np.unique(neighbors_with_long_contact)
            intervention.save_nodes_to_intervene(current_time, neighbors_with_long_contact)
            n_intervention_nodes =  np.sum([len(v) for k, v in intervention.stored_nodes_to_intervene.items() 
                                            if k > current_time - intervention_sick_isolate_time])
            if (n_intervention_nodes>0):
                nodes_to_intervene = np.unique(np.concatenate([v for k, v in intervention.stored_nodes_to_intervene.items() \
                                                               if k > current_time - intervention_sick_isolate_time]) \
                                           ).astype(int)
            else:
                nodes_to_intervene = np.array([],dtype=int)

        else:
            raise ValueError("unknown 'intervention_nodes', choose from 'all' (default), 'sick'")
            
        print("intervention applied to sick nodes: {:d}/{:d}".format(
            nodes_to_intervene.size, network.get_node_count()))

        # Apply the the chosen form of intervention
        if intervention_type == "isolate":
            network.set_lambdas(min_contact_rate, max_contact_rate)
            if nodes_to_intervene.size>0:
                network.isolate(nodes_to_intervene,
                                λ_isolation=arguments.intervention_isolate_node_lambda) 

            np.save(os.path.join(OUTPUT_PATH, 'isolated_nodes.npy'),
                    intervention.stored_nodes_to_intervene)
            
        elif intervention_type == "social_distance":
            λ_min, λ_max = network.get_lambdas() #returns np.array (num_nodes,) for each lambda [Not a dict!]
            λ_max[:] = distanced_max_contact_rate 
            network.set_lambdas(λ_min,λ_max)

            λ_min, λ_max = user_network.get_lambdas() #returns np.aray( num_nodes,) [ not a dict!]
            λ_max[:] = distanced_max_contact_rate 
            user_network.set_lambdas(λ_min,λ_max)

        elif intervention_type == "nothing":
            np.save(os.path.join(OUTPUT_PATH, 'positive_nodes.npy'),
                    intervention.stored_nodes_to_intervene)
            
        else:
            raise ValueError("unknown intervention type, choose from 'social_distance' (default), 'isolate' ")



## Final storage after last step
ensemble_state_frac = ensemble_state.reshape(ensemble_size, 6, -1).sum(axis = 2)/user_population
master_states_sum_timeseries.push_back(ensemble_state_frac) # storage

if learn_transmission_rate == True:
    mean_community_transmission_rate_ensemble = community_transmission_rate_ensemble.mean(axis=1)[:,np.newaxis]
    mean_transmission_rate_timeseries.push_back(
            mean_community_transmission_rate_ensemble)
    if param_transform == 'log':
        mean_community_logtransmission_rate_ensemble = np.log(community_transmission_rate_ensemble).mean(axis=1)[:,np.newaxis]
        mean_logtransmission_rate_timeseries.push_back(
            mean_community_logtransmission_rate_ensemble)

    community_transmission_rate_means = community_transmission_rate_ensemble.mean(axis=0)[np.newaxis,:] #here we avereage the ensemble!
    network_transmission_rate_timeseries.push_back(
                community_transmission_rate_means)
       
if learn_transition_rates == True:
    mean_transition_rates_timeseries.push_back(
        extract_ensemble_transition_rates(transition_rates_ensemble))
    network_transition_rates_timeseries.push_back(
        extract_network_transition_rates(transition_rates_ensemble, user_population))
        
    


## Final save after last step
save_kinetic_state_now = modulo_is_close_to_zero(current_time, 
                                                 save_to_file_interval,                                                     
                                                 eps=static_contact_interval)
if save_kinetic_state_now:
    kinetic_state_path = os.path.join(OUTPUT_PATH, 'kinetic_eqns_statuses_at_step_'+str(prediction_steps)+'.npy')
    kinetic_eqns_statuses = dict_slice(kinetic_state, user_nodes)
    np.save(kinetic_state_path, kinetic_eqns_statuses)
    if user_population < population:
        full_kinetic_state_path = os.path.join(OUTPUT_PATH, 'full_kinetic_eqns_statuses_at_step_'+str(prediction_steps)+'.npy')
        full_kinetic_eqns_statuses = dict_slice(kinetic_state, populace)
        np.save(full_kinetic_state_path, full_kinetic_eqns_statuses)



save_ensemble_state_now = modulo_is_close_to_zero(current_time,
                                                  save_to_file_interval,  
                                                  eps=static_contact_interval)
if save_ensemble_state_now:
    ensemble_state_path = os.path.join(OUTPUT_PATH, 'master_eqns_mean_states_at_step_'+str(prediction_steps)+'.npy')
    master_eqns_mean_states = ensemble_state.mean(axis=0)
    np.save(ensemble_state_path,master_eqns_mean_states)

if intervention_type == 'isolate':
    np.save(os.path.join(OUTPUT_PATH, 'isolated_nodes.npy'),
            intervention.stored_nodes_to_intervene)


print("finished assimilation")
# save state #####################################################################
np.save(os.path.join(OUTPUT_PATH, 'trace_kinetic_statuses_sum.npy'), 
        statuses_sum_trace)

if user_population < population:
    np.save(os.path.join(OUTPUT_PATH, 'trace_full_kinetic_statuses_sum.npy'), 
            full_statuses_sum_trace)


np.save(os.path.join(OUTPUT_PATH, 'trace_master_states_sum.npy'), 
        master_states_sum_timeseries.container)

np.save(os.path.join(OUTPUT_PATH, 'time_span.npy'), 
        time_span)

# save parameters ################################################################
if learn_transmission_rate == True:
    np.save(os.path.join(OUTPUT_PATH, 'ensemble_mean_transmission_rate.npy'), 
            mean_transmission_rate_timeseries.container)
    if param_transform == 'log':
        np.save(os.path.join(OUTPUT_PATH, 'ensemble_mean_logtransmission_rate.npy'), 
                mean_logtransmission_rate_timeseries.container)
    
    np.save(os.path.join(OUTPUT_PATH, 'network_mean_transmission_rate.npy'), 
            network_transmission_rate_timeseries.container)
    

if learn_transition_rates == True:
    np.save(os.path.join(OUTPUT_PATH, 'ensemble_mean_transition_rates.npy'), 
            mean_transition_rates_timeseries.container)

    np.save(os.path.join(OUTPUT_PATH, 'network_mean_transition_rates.npy'), 
         network_transition_rates_timeseries.container)

np.save(os.path.join(OUTPUT_PATH, 'master_eqns_states_sum.npy'), master_states_sum_timeseries.container) #save the ensemble fracs for graphing

# save & plot ##################################################################
plt.close(fig)
fig, axes = plt.subplots(1, 3, figsize = (16, 4))
axes = plot_epidemic_data(user_population, statuses_sum_trace, axes, time_span)
plt.savefig(os.path.join(OUTPUT_PATH, 'epidemic.png'), rasterized=True, dpi=150)

# plot trajectories
axes = plot_ensemble_states(user_population,
                            population,
                            master_states_sum_timeseries.container,
                            time_span,
                            axes=axes,
                            xlims=(-0.1, total_time),
                            a_min=0.0)
plt.savefig(os.path.join(OUTPUT_PATH, 'epidemic_and_master_eqn.png'),
            rasterized=True,
            dpi=150)

plt.close()

if arguments.save_closure_coeffs:
    idx_interval = int(1.0/static_contact_interval)
    CM_SI_coeff = np.array(master_eqn_ensemble.CM_SI_coeff_history[::idx_interval])
    CM_SH_coeff = np.array(master_eqn_ensemble.CM_SH_coeff_history[::idx_interval])
    np.save(os.path.join(OUTPUT_PATH, 'CM_SI_coeff.npy'), CM_SI_coeff)
    np.save(os.path.join(OUTPUT_PATH, 'CM_SH_coeff.npy'), CM_SH_coeff)

if learn_transmission_rate == True:
    plot_transmission_rate(mean_transmission_rate_timeseries.container,
            time_span,
            a_min=0.0,
            output_path=OUTPUT_PATH)
    if param_transform == 'log':
        plot_transmission_rate(mean_logtransmission_rate_timeseries.container,
                               current_time_span,
                               a_min=0.0,
                               output_path=OUTPUT_PATH,
                               output_name='logtransmission_rate')

    plot_transmission_rate(np.swapaxes(network_transmission_rate_timeseries.container,0,1),
                           current_time_span,
                           a_min=0.0,
                           output_path=OUTPUT_PATH,
                           output_name='networktransmission_rate')
if learn_transition_rates == True:                
    plot_network_averaged_clinical_parameters(
        mean_transition_rates_timeseries.container,
        current_time_span,
        age_category_of_users,
        age_indep_rates_true = age_indep_transition_rates_true,
        age_dep_rates_true = age_dep_transition_rates_true,
        a_min=0.0,
        output_path=OUTPUT_PATH,
        output_name='mean')
    plot_ensemble_averaged_clinical_parameters(
        np.swapaxes(network_transition_rates_timeseries.container, 0, 1),
        current_time_span,
        age_category_of_users,
        age_indep_rates_true = age_indep_transition_rates_true,
        age_dep_rates_true = age_dep_transition_rates_true,
        a_min=0.0,
        output_path=OUTPUT_PATH,
        output_name='network')
    



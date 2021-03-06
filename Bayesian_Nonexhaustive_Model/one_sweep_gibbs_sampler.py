# one sweep Gibbs sampler for Bayesian non-exhaustive classification
# For Arnetminer dataset, split training and set based on temporal information of each publication

# Author: Baichuan Zhang 

import os;
import sys;
import random;
import numpy as np;
from sklearn.decomposition import NMF;
from scipy.optimize import nnls;
from scipy.special import gammaln;
import scipy.stats as ss;
import math;


def File_Reader(file_name, latent_dimen, test_year_len):

	data_matrix = np.loadtxt(str(file_name), delimiter = " ").tolist();
	num_row = len(data_matrix);
	num_col = len(data_matrix[0]);

	# sort the data_matrix based on publication year information
	data_matrix.sort(key = lambda x: x[num_col - 1]);
	label_list = map(int, np.array((np.array(data_matrix)[0:num_row, num_col-2:num_col-1])).T.tolist()[0]);
 	
 	year_list = map(int, np.array((np.array(data_matrix)[0:num_row, num_col-1:num_col])).T.tolist()[0])
 	sorted_year_list = sorted(list(set(year_list)));

 	test_year_list = sorted_year_list[len(sorted_year_list) - test_year_len:];

 	raw_train_list = [];
 	train_label_list = [];

 	raw_test_list = [];
 	test_label_list = [];

 	for i in range(0, len(data_matrix)):

 		if year_list[i] not in test_year_list:

 			raw_train_list.append(data_matrix[i][0:num_col - 2]);
 			train_label_list.append(label_list[i]);

 		else:

 			raw_test_list.append(data_matrix[i][0:num_col - 2]);
 			test_label_list.append(label_list[i]);

 	num_train = len(train_label_list);

 	# run batch-based NNMF on training set which is initially available
 	raw_train_matrix = np.array(raw_train_list);
 	nmf_model = NMF(n_components = latent_dimen, random_state = None);
 	nmf_model.fit(raw_train_matrix);

 	# U_matrix is the user latent matrix
 	U_matrix = nmf_model.transform(raw_train_matrix).tolist();

 	# V_matrix is a set of item basis vector
 	V_matrix = nmf_model.components_;

 	# from U_matrix, build train_set_dict
 	train_set_dict = {};

 	for tr in range(0, len(train_label_list)):

 		if train_label_list[tr] not in train_set_dict:

 			train_set_dict[train_label_list[tr]] = [U_matrix[tr]];

 		else:

 			train_set_dict[train_label_list[tr]].append(U_matrix[tr]);

 	# from V_matrix, use non-negative least square to obtain the latent features for each streaming test paper
 	test_set_list = [];

 	for te in range(0, len(raw_test_list)):

 		raw_test_vector = np.array(raw_test_list[te]);
 		test_latent_feature, rnorm = nnls(V_matrix.T, raw_test_vector);
		test_set_list.append(test_latent_feature);


	return [train_set_dict, test_set_list, test_label_list, num_train];


# estimate the mean and variance in Normal-Normal-Invert Wishart model

def parameter_estimatet(train_set_dict, latent_dimen, num_train, m):

	# estimate the u_0 as mean of training dataset
	# use pooled covariance matrix to estimate \Sigma_0 in multivariate student-t
	
	data_list_list = [];

	# initialize a K*K zero matrix
	sigma_0 = np.zeros((latent_dimen, latent_dimen));
	
	for k, v in train_set_dict.items():

		D_j = np.array(v);
		sigma_0 = sigma_0 + len(v) * np.cov(D_j.T, bias = 1);

		for i in range(0,len(v)):

			data_list_list.append(v[i]);

	u_0_list = np.mean(np.array(data_list_list), axis=0).tolist();	
	sigma_0 = (float(1)/(num_train - len(train_set_dict)))*(m-latent_dimen-1)*sigma_0;
	
	# use c*I to estimate sigma_0
#	smooth_term = float(latent_dimen * math.log(latent_dimen)) / 150;
#	sigma_0 = np.eye(latent_dimen) * smooth_term;
	
	return [u_0_list, sigma_0];


# use empirical Bayes by sampling a large number of samples from a Chinese Restaurant Process for picking up alpha

def estimate_alpha(num_train):
	
	alpha_list = range(20, 1000, 20);	

	# vague_prob is our prior belief of encountering a new class

	vague_prob = 0.4;
	max_diff_prob = sys.maxint;
	best_alpha = -1;

	for pos in range(0,len(alpha_list)):

		es_alpha = int(alpha_list[pos]);
		CRP_ratio = float(es_alpha)/(es_alpha + num_train);	
		active_count = 0;

		for i in range(0, 100000):

			ran_p = random.uniform(0,1);
			if ran_p <= CRP_ratio:
				active_count = active_count + 1;

		CRP_prob = float(active_count)/100000;
		diff_prob = abs(CRP_prob - vague_prob);

		if diff_prob <	max_diff_prob:
			max_diff_prob = diff_prob;
			best_alpha = es_alpha;

	return best_alpha;


# Since Numpy and Scipy package don't have existing multivariate student-t distribution function, so I implement its PDF function here based on "http://en.wikipedia.org/wiki/Multivariate_t-distribution" and compute the likelihood of given testdata. Also in order to avoid the overfloating issue of Gamma function, take the Log function of its PDF
# first parameter is the location vector (d*1), the second one is the positive definite scale matrix (d*d) and the third one is the degrees of freedom for the multivariate t distribution

def Multivariate_Student_t_likelihood(stud_t_1, stud_t_2, stud_t_3, testdata, latent_dimen):

	x_vector = np.array(testdata).reshape(latent_dimen,1);		
	log_det = np.log(np.linalg.det(stud_t_2));
	a = np.dot((x_vector - stud_t_1).reshape(1,latent_dimen), np.linalg.inv(stud_t_2));
	Q = np.dot(a, (x_vector - stud_t_1));
	Q_value = Q[0];
	
	log_likelihood = gammaln(float(stud_t_3+latent_dimen)/2) - gammaln(float(stud_t_3)/2) - (float(latent_dimen)/2)*np.log(stud_t_3) - (float(latent_dimen)/2)*np.log(np.pi) - 0.5*log_det - (float(stud_t_3+latent_dimen)/2)*np.log(1+float(Q_value)/stud_t_3);

	likelihood = np.exp(log_likelihood);

	return likelihood;


# compute the Macro-F1 in clustering setting (chapter 17 in Zaki's data mining book)

def Compute_F1(test_label_list, predict_label_list):

	# group the papers with same predicted label from HAC together

	predict_label_dict = {};

	for pos in range(0,len(predict_label_list)):

		predict_label_ = int(predict_label_list[pos]);

		if predict_label_dict.get(predict_label_, -1) == -1:

			pred_paperid_list = [];
			# paper index starts from 1
			pred_paperid_list.append(pos+1);
			predict_label_dict[predict_label_] = pred_paperid_list;

		else:

			pred_paperid_list = predict_label_dict[predict_label_];	
			pred_paperid_list.append(pos+1);
			predict_label_dict[predict_label_] = pred_paperid_list;

	predict_num_cluster = len(predict_label_dict);
	
	true_label_dict = {};

	for inpos in range(0,len(test_label_list)):

		true_label = int(test_label_list[inpos]);

		if true_label_dict.get(true_label, -1) == -1:

			paperid_list = [];
			# paper index starts from 1
			paperid_list.append(inpos+1);
			true_label_dict[true_label] = paperid_list;

		else:

			paperid_list = true_label_dict[true_label];	
			paperid_list.append(inpos+1);
			true_label_dict[true_label] = paperid_list;

	true_num_cluster = len(true_label_dict);

	# let's denote C(r) as clustering result and T(k) as partition (ground-truth), and construct r*k contingency table
	r_k_table = [];

	for v1 in predict_label_dict.itervalues():

		k_list = [];

		for v2 in true_label_dict.itervalues():

			N_ij = int(len(set(v1).intersection(v2)));
			k_list.append(N_ij);

		r_k_table.append(k_list);

	r_k_matrix = np.array(r_k_table);
	r_num = int(r_k_matrix.shape[0]);

	# compute the F1 for each C_i (row)
	sum_f1 = 0.0;

	for row in range(0, r_num):

		row_sum = np.sum(r_k_matrix[row,:]);

		if row_sum != 0:

			max_col_index = np.argmax(r_k_matrix[row,:]);	
			row_max_value = r_k_matrix[row,max_col_index];
			prec = float(row_max_value)/row_sum;
			col_sum = np.sum(r_k_matrix[:,max_col_index]);
			rec = float(row_max_value)/col_sum;
			row_f1 = float(2*prec*rec)/(prec+rec);
			sum_f1 = sum_f1 + row_f1;
	
	aver_f1 = float(sum_f1)/r_num;

	return [aver_f1, predict_num_cluster, true_num_cluster];


# implement Infinite Gaussian Mixture Model (IGMM)
# Perform one-sweep Gibbs sampler for online classification

def Gibbs(train_set_dict, test_set_list, test_label_list, latent_dimen, kapa, sigma_0, m, u_0_list, alpha, num_train):

	emerge_label = 5000;
	predict_label_list = [];

	# num_data is the total number of data being processed online + number of training instances initially available
	num_data = num_train;
	
	for pos in range(0,len(test_set_list)):
		
		testdata = test_set_list[pos];

		# Given each testdata, for training data points of each class label, compute its coresponding likelihood
		predlabel_prob_dict = {};

		for k_train, v_train in train_set_dict.items():

			predict_label = int(k_train);
			data_matrix = np.array(v_train); 
			data_num = int(len(v_train));
			x_bar_list = [];
			
			for col_ in range(0,data_matrix.shape[1]):
				col_sum = np.sum(data_matrix[:,col_]);
				col_mean = float(col_sum)/data_num;
				x_bar_list.append(col_mean);
			
			# first parameter of student-t distribution based on equation B.3
			stud_t_1 = (float(1)/(data_num + kapa))*np.add(kapa*np.array(u_0_list).reshape(latent_dimen,1), data_num*np.array(x_bar_list).reshape(latent_dimen,1)); 										
			
			# compute the second parameter of student-t distribution based on equation B.3
			front_const = float(data_num + kapa + 1)/((data_num+kapa)*(data_num+m+1-latent_dimen));
			inner_matrix = sigma_0 + data_num*np.cov(data_matrix.T, bias = 1) + (float(data_num*kapa)/(kapa+data_num))*np.outer((np.array(u_0_list)-np.array(x_bar_list)), (np.array(u_0_list)-np.array(x_bar_list)));
			stud_t_2 = front_const * inner_matrix;

			# compute the third parameter of student-t distribution based on equation B.3
			stud_t_3 = data_num + m + 1 - latent_dimen;
			
			# compute the likelihood of multivariate student-t distribution for the given testdata and given precomputed three parameters
			studt_likelihood= Multivariate_Student_t_likelihood(stud_t_1, stud_t_2, stud_t_3, testdata, latent_dimen);
			
			# combine both multivariate student-t likelihood and Dirichlet prior as posterior probability 
			posterior_prob = (float(data_num)/(alpha+num_data)) * studt_likelihood;

			predlabel_prob_dict[predict_label] = posterior_prob;


		# compute the marginal probability p(x_{n+1}) = p(x_{n+1}|D_{j}) with D_{j} = \emptyset

		marginal_prob = Multivariate_Student_t_likelihood(np.array(u_0_list).reshape(latent_dimen, 1), (float(kapa+1)/(kapa*(m+1-latent_dimen)))*sigma_0, m+1-latent_dimen, testdata, latent_dimen);
		new_cluster_prob = (float(alpha)/(alpha+num_data))*marginal_prob;
		predlabel_prob_dict[emerge_label] = new_cluster_prob;

		# sample from predlabel_prob_dict and decide the class membership of current online test instance
		sample_label_list = [];
		sample_prob_list = [];

		for sample_k, sample_v in predlabel_prob_dict.items():

			sample_label_list.append(int(sample_k));
			sample_prob_list.append(float(sample_v));

		norm_prob_list = [float(nr)/sum(sample_prob_list) for nr in sample_prob_list];

		# sample the label according to the posterior probability
		gibbs_label = np.random.choice(sample_label_list, 1, norm_prob_list)[0];

		# update train_set_dict based on the one-sweep Gibbs sampler result

		if gibbs_label != emerge_label:
		
			# update the train_set_dict
			train_set_dict[gibbs_label].append(testdata);

			# add the final predicted result into predict_label_list
			predict_label_list.append(gibbs_label);
		
		else:
		
			# detect an emerging class
			train_set_dict[gibbs_label] = [testdata];
			emerge_label = emerge_label + 1;

			# add emerge_label result into predict_label_list
			predict_label_list.append(gibbs_label);
		
		# increment the processed data points by 1
		num_data = num_data + 1;
	
	aver_f1, predict_num_cluster, true_num_cluster = Compute_F1(test_label_list, predict_label_list);
	
	return [aver_f1, predict_num_cluster, true_num_cluster];



if __name__ == '__main__':
	

	if len(sys.argv) != 4:

		print "data matrix filename";
		print "latent dimension";
		print "test year length";
		
		sys.exit(0);


	file_name = str(sys.argv[1]);
	latent_dimen = int(sys.argv[2]);
	test_year_len = int(sys.argv[3]);

	# m > latent_dimen + 2
	m = latent_dimen + 100;
	best_alpha = 50;
	kapa = 100.0;
	
	train_set_dict, test_set_list, test_label_list, num_train = File_Reader(file_name, latent_dimen, test_year_len);
	u_0_list, sigma_0 = parameter_estimatet(train_set_dict, latent_dimen, num_train, m);
	
	f1_list = [];

	for r1 in range(0, 20):

		aver_f1, predict_num_cluster, true_num_cluster = Gibbs(train_set_dict, test_set_list, test_label_list, latent_dimen, kapa, sigma_0, m, u_0_list, best_alpha, num_train);	
		f1_list.append(aver_f1);

		print 'true number of clusters is ' + str(true_num_cluster);
		print 'predict number of clusters is ' + str(predict_num_cluster);
		print 'average f1 is ' + str(aver_f1);
		print;

	mean_f1 = np.mean(f1_list);
	std_f1 = np.std(f1_list);

	print str(mean_f1) + ',' + str(std_f1);

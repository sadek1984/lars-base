

import numpy as np
import pandas as pd
from scipy import stats
from typing import Dict, List, Tuple
from scipy.stats import norm, lognorm
from scipy.special import beta 
from scipy.stats import kstest, anderson, norm, lognorm, gamma, weibull_min
import warnings


class EnhancedRiskAssessment:
    """Enhanced risk assessment with Monte Carlo and Bayesian methods"""
    
    def __init__(self, historical_data_path: str):
        """Initialize with historical data"""
        self.df = pd.read_excel('./data/processed_data_output.xlsx')
        self.df['document_date'] = pd.to_datetime(self.df['document_date'])
        
        self.vegetable_to_category = {
        'parsley': 'herbs',
        'lettuce': 'leafy_greens',
        'spinach': 'leafy_greens',
        'arugula': 'leafy_greens',
        'kale': 'leafy_greens',
        'tomato': 'fruits',
        'cucumber': 'fruits',
        'strawberry': 'berries',
        'bell pepper': 'peppers',
        'chili pepper': 'peppers',
        'basil': 'herbs',
        'cilantro': 'herbs',
        'carrot': 'root_vegetables',
        'potato': 'root_vegetables',
        'onion': 'root_vegetables',
        'broccoli': 'cruciferous',
        'cauliflower': 'cruciferous',
        'cabbage': 'cruciferous',
        # Add more vegetables as needed
    }
        # Define hazard multipliers based on exposure risk
        self.vegetable_multipliers = {
            'leafy_greens': 1.5,      # Higher exposure (eaten raw, large surface area)
            'peppers': 1.2,           # Moderate exposure
            'herbs': 1.4,             # High exposure (eaten raw)
            'root_vegetables': 0.8,   # Lower exposure (often peeled)
            'fruits': 1.0             # Baseline
        }
        
        # Beta-Binomial priors for pesticide groups (alpha, beta parameters)
        # These represent our "prior belief" about each pesticide group's risk
        # alpha = "pseudo-successes" (exceedances), beta = "pseudo-failures" (compliances)
        self.pesticide_beta_priors = {
            'phenylpyrazoles': (7.5, 2.5),    # High risk: equivalent to 7.5 exceedances in 10 samples
            'pyrethroid': (7.0, 3.0),         # High risk: 7 exceedances in 10 samples
            'organophosphorus': (6.5, 3.5),   # High risk: 6.5 exceedances in 10 samples
            'neonicotinoid': (6.0, 4.0),      # Moderate-high: 6 exceedances in 10 samples
            'chitin_synthesis_inhibitor': (5.5, 4.5),  # Moderate: 5.5 exceedances in 10 samples
            'strobilurin': (5.0, 5.0),        # Neutral: equal chance of exceedance/compliance
            'other': (4.5, 5.5)               # Lower risk: 4.5 exceedances in 10 samples
        }
        
        # Group-specific critical thresholds
        self.critical_thresholds = {
            'chitin_synthesis_inhibitor': 3.0,
            'pyrethroid': 3.5,
            'organophosphorus': 3.0,
            'phenylpyrazoles': 3.2,
            'neonicotinoid': 3.3,
            'default': 4.0
        }
        
    def validated_monte_carlo_exceedance(
        self, 
        vegetable: str,
        pesticide_group: str,
        current_reading: float,
        limit: float,
        n_simulations: int = 10000
    ) -> Dict:
        """
        Enhanced Monte Carlo with distribution validation
        """
        
        # Get historical data
        subgroup_data = self._get_historical_data(vegetable, pesticide_group)
        
        if len(subgroup_data) < 5:
            return self._fallback_calculation(current_reading, limit)
        
        # Validate distribution fit
        error_scores = self._validate_distribution_fit(vegetable, pesticide_group)
        best_dist, best_score = self._get_best_distribution(error_scores)
        
        # Generate simulations using the best distribution
        simulations = self._generate_simulations(subgroup_data, best_dist, n_simulations)
        
        # Calculate exceedance probability
        exceedance_prob = (simulations > limit).mean()
        
        # Bootstrap confidence interval
        bootstrap_probs = []
        for _ in range(1000):
            bootstrap_sample = np.random.choice(simulations, size=1000, replace=True)
            bootstrap_probs.append((bootstrap_sample > limit).mean())
        
        ci_lower, ci_upper = np.percentile(bootstrap_probs, [2.5, 97.5])
        
        return {
            'exceedance_probability': exceedance_prob,
            'confidence_interval': (float(ci_lower), float(ci_upper)),
            'best_distribution': best_dist,
            'distribution_score': best_score,
            'n_historical_samples': len(subgroup_data),
            'method': 'validated_monte_carlo',
            'all_distribution_scores': error_scores
        }
    def monte_carlo_exceedance_probability(
    self, 
    vegetable: str,
    pesticide_group: str,
    current_reading: float,
    limit: float,
    n_simulations: int = 10000
) -> Dict:
        """
        Legacy method name for backward compatibility
        Now uses the validated Monte Carlo approach
        """
        return self.validated_monte_carlo_exceedance(
            vegetable=vegetable,
            pesticide_group=pesticide_group,
            current_reading=current_reading,
            limit=limit,
            n_simulations=n_simulations
        )
    
    def _get_historical_data(self, vegetable: str, pesticide_group: str) -> pd.Series:
        """Helper to get historical data with fallbacks"""
        subgroup = self.df[
            (self.df['vegetable_english'] == vegetable) & 
            (self.df['pesticide_group'] == pesticide_group)
        ]['reading'].dropna()
        
        if len(subgroup) < 5:
            subgroup = self.df[self.df['pesticide_group'] == pesticide_group]['reading'].dropna()
        
        return subgroup

    def _generate_simulations(self, data: pd.Series, dist_type: str, n_simulations: int) -> np.ndarray:
        """Generate simulations based on distribution type"""
        positive_data = data[data > 0]
        
        if dist_type == 'normal':
            mu, sigma = norm.fit(data)
            simulations = np.random.normal(mu, sigma, n_simulations)
        
        elif dist_type == 'lognormal':
            shape, loc, scale = lognorm.fit(positive_data, floc=0)
            simulations = lognorm.rvs(shape, loc=0, scale=scale, size=n_simulations)
        
        elif dist_type == 'gamma':
            alpha, loc, beta = gamma.fit(positive_data, floc=0)
            simulations = gamma.rvs(alpha, loc=0, scale=beta, size=n_simulations)
        
        elif dist_type == 'weibull':
            shape, loc, scale = weibull_min.fit(positive_data, floc=0)
            simulations = weibull_min.rvs(shape, loc=0, scale=scale, size=n_simulations)
        
        elif dist_type == 'empirical':
            simulations = np.random.choice(data, size=n_simulations, replace=True)
        
        else:  # Fallback to lognormal
            shape, loc, scale = lognorm.fit(positive_data, floc=0)
            simulations = lognorm.rvs(shape, loc=0, scale=scale, size=n_simulations)
        
        # Ensure no negative values
        return np.maximum(0.1, simulations)

    def _fallback_calculation(self, current_reading: float, limit: float) -> Dict:
        """Fallback when insufficient data"""
        simple_prob = 1.0 if current_reading > limit else 0.0
        return {
            'exceedance_probability': simple_prob,
            'confidence_interval': (simple_prob, simple_prob),
            'best_distribution': 'deterministic',
            'distribution_score': 1.0,
            'n_historical_samples': 0,
            'method': 'deterministic_fallback'
        }

    def _validate_distribution_fit(self, vegetable: str, pesticide_group: str) -> Dict[str, float]:
        """
        Validate which probability distribution best fits the historical data
        Returns error scores for each distribution (lower is better)
        """
        
        # Get historical data for the specific subgroup
        subgroup_data = self.df[
            (self.df['vegetable_english'] == vegetable) & 
            (self.df['pesticide_group'] == pesticide_group)
        ]['reading'].dropna()
        
        # If insufficient data, broaden the search
        if len(subgroup_data) < 10:
            subgroup_data = self.df[
                self.df['pesticide_group'] == pesticide_group
            ]['reading'].dropna()
        
        if len(subgroup_data) < 5:
            # Return default scores if insufficient data
            return {'normal': 1.0, 'lognormal': 1.0, 'gamma': 1.0, 'weibull': 1.0}
        
        # Remove zeros and negative values for log-based distributions
        positive_data = subgroup_data[subgroup_data > 0]
        
        # Initialize error scores
        error_scores = {}
        
        try:
            # Test Normal distribution
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                mu, sigma = norm.fit(subgroup_data)
                ks_stat_norm, p_value_norm = kstest(subgroup_data, 'norm', args=(mu, sigma))
                error_scores['normal'] = ks_stat_norm
        except Exception as e:
            error_scores['normal'] = 1.0
        
        try:
            # Test Lognormal distribution
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                if len(positive_data) >= 5:
                    shape, loc, scale = lognorm.fit(positive_data, floc=0)
                    ks_stat_lognorm, p_value_lognorm = kstest(positive_data, 'lognorm', args=(shape, loc, scale))
                    error_scores['lognormal'] = ks_stat_lognorm
                else:
                    error_scores['lognormal'] = 1.0
        except Exception as e:
            error_scores['lognormal'] = 1.0
        
        try:
            # Test Gamma distribution
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                if len(positive_data) >= 5:
                    alpha, loc, beta = gamma.fit(positive_data, floc=0)
                    ks_stat_gamma, p_value_gamma = kstest(positive_data, 'gamma', args=(alpha, loc, beta))
                    error_scores['gamma'] = ks_stat_gamma
                else:
                    error_scores['gamma'] = 1.0
        except Exception as e:
            error_scores['gamma'] = 1.0
        
        try:
            # Test Weibull distribution
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                if len(positive_data) >= 5:
                    shape, loc, scale = weibull_min.fit(positive_data, floc=0)
                    ks_stat_weibull, p_value_weibull = kstest(positive_data, 'weibull_min', args=(shape, loc, scale))
                    error_scores['weibull'] = ks_stat_weibull
                else:
                    error_scores['weibull'] = 1.0
        except Exception as e:
            error_scores['weibull'] = 1.0
        
        # Empirical distribution always available as fallback
        error_scores['empirical'] = 0.5  # Default mid-range score
        
        return error_scores

    def _get_best_distribution(self, error_scores: Dict[str, float]) -> Tuple[str, float]:
        """
        Select the best-fitting distribution based on error scores
        Returns: (distribution_name, error_score)
        """
        if not error_scores or all(v == 1.0 for v in error_scores.values()):
            return 'empirical', 0.5
        
        best_dist = min(error_scores, key=error_scores.get)
        best_score = error_scores[best_dist]
        
        return best_dist, best_score

    def bayesian_beta_risk(
        self, 
        pesticide_group: str, 
        historical_data: pd.DataFrame
    ) -> Dict:
        """
        Enhanced Bayesian risk analysis using Beta-Binomial conjugate prior
        
        This is the proper Bayesian approach for binary outcomes (exceedance vs compliance)
        
        Parameters:
        -----------
        pesticide_group : str
            The pesticide group to analyze
        historical_data : pd.DataFrame
            Historical data with 'reading' and 'limit' columns
            
        Returns:
        --------
        Dict with posterior statistics
        """
        
        # Get the prior for this pesticide group
        alpha_prior, beta_prior = self.pesticide_beta_priors.get(
            pesticide_group, (5.0, 5.0)
        )
        
        # Count exceedances and total observations from historical data
        if 'limit' not in historical_data.columns or 'reading' not in historical_data.columns:
            # Fallback if data format is wrong
            return {
                'posterior_mean': alpha_prior / (alpha_prior + beta_prior),
                'posterior_mode': alpha_prior / (alpha_prior + beta_prior),
                'posterior_variance': 0.0,
                'credible_interval': (0.0, 1.0),
                'prior_parameters': (alpha_prior, beta_prior),
                'posterior_parameters': (alpha_prior, beta_prior),
                'observed_data': (0, 0),
                'effective_sample_size': 0,
                'prior_strength': 1.0,
                'bayes_factor': 1.0
            }
        
        # Calculate exceedances
        exceedances = (historical_data['reading'] > historical_data['limit']).sum()
        n_observations = len(historical_data)
        n_exceedances = int(exceedances)
        
        # Bayesian update: posterior = prior + data
        # For Beta-Binomial: α_post = α_prior + successes, β_post = β_prior + failures
        alpha_post = alpha_prior + n_exceedances
        beta_post = beta_prior + (n_observations - n_exceedances)
        
        # Calculate posterior statistics
        posterior_mean = alpha_post / (alpha_post + beta_post)
        posterior_mode = (alpha_post - 1) / (alpha_post + beta_post - 2) if alpha_post > 1 and beta_post > 1 else posterior_mean
        posterior_variance = (alpha_post * beta_post) / ((alpha_post + beta_post) ** 2 * (alpha_post + beta_post + 1))
        
        # 95% credible interval (Bayesian confidence interval)
        credible_interval = stats.beta.interval(0.95, alpha_post, beta_post)
        
        return {
            'posterior_mean': posterior_mean,           # Mean probability of exceedance
            'posterior_mode': posterior_mode,           # Most likely probability
            'posterior_variance': posterior_variance,   # Uncertainty in estimate
            'credible_interval': credible_interval,     # 95% credible interval
            'prior_parameters': (alpha_prior, beta_prior),
            'posterior_parameters': (alpha_post, beta_post),
            'observed_data': (n_exceedances, n_observations),
            'effective_sample_size': n_observations,
            'prior_strength': (alpha_prior + beta_prior) / (alpha_post + beta_post),  # How much prior influences result
            'bayes_factor': self._calculate_bayes_factor(alpha_prior, beta_prior, n_exceedances, n_observations)
        }

    def _calculate_bayes_factor(self, alpha_prior: float, beta_prior: float, 
                                n_exceedances: int, n_observations: int) -> float:
        """
        Calculate Bayes Factor to compare models
        
        Bayes Factor < 1: Data supports null hypothesis (low risk)
        Bayes Factor > 1: Data supports alternative hypothesis (high risk)
        """
        # Compare risk hypothesis (high risk prior) vs safety hypothesis (low risk prior)
        # High risk prior: (7, 3) - believes in high exceedance probability
        # Low risk prior: (3, 7) - believes in low exceedance probability
        
        high_risk_prior = (7.0, 3.0)
        low_risk_prior = (3.0, 7.0)
        
        # Calculate marginal likelihood for each model
        marg_likelihood_high = (beta(high_risk_prior[0] + n_exceedances, high_risk_prior[1] + n_observations - n_exceedances) / 
                                beta(high_risk_prior[0], high_risk_prior[1]))
        
        marg_likelihood_low = (beta(low_risk_prior[0] + n_exceedances, low_risk_prior[1] + n_observations - n_exceedances) / 
                               beta(low_risk_prior[0], low_risk_prior[1]))
        
        return marg_likelihood_high / marg_likelihood_low

    def bayesian_risk_update(
        self,
        pesticide_group: str,
        exceedance_ratio: float,
        is_compliant: bool
    ) -> float:
        """
        Enhanced Bayesian risk update using Beta-Binomial approach
        
        This is a simplified version that can be used when you don't have full historical data
        but want to incorporate Bayesian thinking.
        """
        
        # Get the appropriate beta prior for this pesticide group
        alpha_prior, beta_prior = self.pesticide_beta_priors.get(
            pesticide_group, (5.0, 5.0)
        )
        
        # Convert current observation to "pseudo-data"
        if not is_compliant or exceedance_ratio > 1:
            # Non-compliant observation counts as an exceedance
            n_exceedances = 1
            n_observations = 1
        else:
            # Compliant observation counts as a non-exceedance
            n_exceedances = 0
            n_observations = 1
        
        # Bayesian update
        alpha_post = alpha_prior + n_exceedances
        beta_post = beta_prior + (n_observations - n_exceedances)
        
        # Return posterior mean as the Bayesian risk score
        posterior_mean = alpha_post / (alpha_post + beta_post)
        
        return posterior_mean
    
    def calculate_enhanced_risk_score(
        self,
        vegetable: str,
        pesticide_group: str,
        reading: float,
        limit: float,
        is_compliant: bool
    ) -> Dict:
        """
        Enhanced risk calculation with validated Monte Carlo and proper Bayesian methods
        """
        # AUTO-DERIVE vegetable_category from vegetable name
        vegetable_lower = vegetable.lower().strip()
        vegetable_category = self.vegetable_to_category.get(vegetable_lower, 'fruits')  # default to 'fruits'
   
        
        # 1. Calculate exceedance ratio
        exceedance_ratio = reading / limit if limit > 0 else 0
        
        # 2. Get historical data for Bayesian analysis
        historical_data = self._get_historical_data_for_bayesian(vegetable, pesticide_group, limit)
        
        # 3. Monte Carlo exceedance probability
        mc_result = self.validated_monte_carlo_exceedance(
            vegetable=vegetable,
            pesticide_group=pesticide_group,
            current_reading=reading,
            limit=limit
        )
        
        # 4. Proper Bayesian risk analysis (if sufficient historical data)
        if len(historical_data) >= 5:
            bayesian_result = self.bayesian_beta_risk(pesticide_group, historical_data)
            bayesian_risk = bayesian_result['posterior_mean']
            bayesian_confidence = bayesian_result['credible_interval']
            bayesian_method = 'beta_binomial'
        else:
            # Fallback to simplified Bayesian update
            bayesian_risk = self.bayesian_risk_update(
                pesticide_group=pesticide_group,
                exceedance_ratio=exceedance_ratio,
                is_compliant=is_compliant
            )
            bayesian_confidence = (bayesian_risk, bayesian_risk)  # No confidence interval
            bayesian_method = 'simplified'
        
        # 5. Apply vegetable category multiplier (hazard model)
        veg_multiplier = self.vegetable_multipliers.get(vegetable_category, 1.0)
        
        # 6. Combine all factors into final risk score (0-5 scale)
        base_risk = min(5.0, exceedance_ratio)
        probabilistic_risk = mc_result['exceedance_probability'] * 2  # Scale to 0-2
        bayesian_component = bayesian_risk * 2  # Scale to 0-2
        
        # Weighted combination
        raw_risk = (
            base_risk * 0.4 +           # 40% from exceedance
            probabilistic_risk * 0.3 +   # 30% from probability
            bayesian_component * 0.3     # 30% from Bayesian
        ) * veg_multiplier               # Apply vegetable hazard multiplier
        
        final_risk_score = min(5.0, raw_risk)
        
        # 7. Determine risk level using group-specific thresholds
        threshold = self.critical_thresholds.get(pesticide_group, self.critical_thresholds['default'])
        
        if final_risk_score >= threshold:
            risk_level = 'CRITICAL'
        elif final_risk_score >= 3.0:
            risk_level = 'HIGH'
        elif final_risk_score >= 2.0:
            risk_level = 'MEDIUM'
        elif final_risk_score >= 1.0:
            risk_level = 'LOW'
        else:
            risk_level = 'MINIMAL'
        
        return {
            'risk_score': round(final_risk_score, 2),
            'risk_level': risk_level,
            'exceedance_probability': round(mc_result['exceedance_probability'], 3),
            'confidence_interval': mc_result['confidence_interval'],
            'bayesian_risk': round(bayesian_risk, 3),
            'bayesian_confidence': bayesian_confidence,
            'bayesian_method': bayesian_method,
            'vegetable_multiplier': veg_multiplier,
            'critical_threshold': threshold,
            'components': {
                'base_risk': round(base_risk, 2),
                'probabilistic_risk': round(probabilistic_risk, 2),
                'bayesian_component': round(bayesian_component, 2)
            },
            'distribution_used': mc_result.get('best_distribution', 'unknown'),
            'distribution_score': mc_result.get('distribution_score', 1.0)
        }

    def _get_historical_data_for_bayesian(self, vegetable: str, pesticide_group: str, limit: float) -> pd.DataFrame:
        """
        Get historical data formatted for Bayesian analysis
        """
        historical_data = self.df[
            (self.df['pesticide_group'] == pesticide_group) &
            (self.df['vegetable_english'] == vegetable)
        ][['reading', 'limits']].copy()
        
        # Rename columns to match expected format
        historical_data.columns = ['reading', 'limit']
        
        # If no data for specific vegetable, get all data for pesticide group
        if len(historical_data) < 5:
            historical_data = self.df[
                self.df['pesticide_group'] == pesticide_group
            ][['reading', 'limits']].copy()
            historical_data.columns = ['reading', 'limit']
        
        return historical_data
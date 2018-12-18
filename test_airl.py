import gym
import pytest
import tensorflow as tf

from airl import AIRLTrainer
from reward_net import BasicRewardNet
import util


def _init_trainer(env, use_expert_rollouts=False):
    policy = util.make_blank_policy(env, init_tensorboard=False)
    if use_expert_rollouts:
        rollout_policy = util.load_expert_policy(env)
        if rollout_policy is None:
            raise ValueError(env)
    else:
        rollout_policy = policy

    obs_old, act, obs_new, _ = util.rollout_generate(rollout_policy, env,
            n_timesteps=1000)

    rn = BasicRewardNet(env)
    trainer = AIRLTrainer(env, policy=util.make_blank_policy(env,
        init_tensorboard=False), reward_net=rn, expert_obs_old=obs_old,
            expert_act=act, expert_obs_new=obs_new)
    return policy, trainer


class TestAIRL(tf.test.TestCase):

    def test_init_no_crash(self, env='CartPole-v1'):
        _init_trainer(env)

    def test_train_disc_no_crash(self, env='CartPole-v1', n_timesteps=110):
        policy, trainer = _init_trainer(env)
        obs_old, act, obs_new, _ = util.rollout_generate(policy, env,
                n_timesteps=n_timesteps)
        trainer.train_disc(trainer.expert_obs_old, trainer.expert_act,
                trainer.expert_obs_new, obs_old, act, obs_new)

    def test_train_gen_no_crash(self, env='CartPole-v1', n_steps=10):
        policy, trainer = _init_trainer(env)
        trainer.train_gen(n_steps)

    @pytest.mark.expensive
    def test_train_disc_improve_D(self, env='CartPole-v1', n_timesteps=100,
            n_steps=10000):
        policy, trainer = _init_trainer(env)
        obs_old, act, obs_new, _ = util.rollout_generate(policy, env,
                n_timesteps=n_timesteps)
        args = [trainer.expert_obs_old, trainer.expert_act,
                trainer.expert_obs_new, obs_old, act, obs_new]
        loss1 = trainer.eval_disc_loss(*args)
        trainer.train_disc(*args, n_steps=n_steps)
        loss2 = trainer.eval_disc_loss(*args)
        assert loss2 < loss1

    @pytest.mark.expensive
    def test_train_gen_degrade_D(self, env='CartPole-v1', n_timesteps=100,
            n_steps=10000):
        policy, trainer = _init_trainer(env)
        obs_old, act, obs_new, _ = util.rollout_generate(policy, env,
                n_timesteps=n_timesteps)
        args = [trainer.expert_obs_old, trainer.expert_act,
                trainer.expert_obs_new, obs_old, act, obs_new]
        loss1 = trainer.eval_disc_loss(*args)
        trainer.train_gen(n_steps=n_steps)
        loss2 = trainer.eval_disc_loss(*args)
        assert loss2 > loss1

    @pytest.mark.expensive
    def test_train_disc_then_gen(self, env='CartPole-v1', n_timesteps=100,
            n_steps=10000):
        policy, trainer = _init_trainer(env)
        obs_old, act, obs_new, _ = util.rollout_generate(policy, env,
                n_timesteps=n_timesteps)
        args = [trainer.expert_obs_old, trainer.expert_act,
                trainer.expert_obs_new, obs_old, act, obs_new]
        loss1 = trainer.eval_disc_loss(*args)
        trainer.train_disc(*args, n_steps=n_steps)
        loss2 = trainer.eval_disc_loss(*args)
        trainer.train_gen(n_steps=n_steps)
        loss3 = trainer.eval_disc_loss(*args)
        assert loss2 < loss1
        assert loss3 > loss2

    @pytest.mark.expensive
    def test_train_no_crash(self, env='CartPole-v1'):
        policy, trainer = _init_trainer(env)
        trainer.train(n_epochs=3)

    @pytest.mark.expensive
    @pytest.xfail(reason="Either AIRL train is broken or not enough epochs."
            " Consider making a plot of episode reward over time to check.")
    def test_trained_policy_better_than_random(self, env='CartPole-v1',
            n_episodes=10):
        """
        Make sure that generator policy trained to mimick expert policy
        demonstrations) achieves higher reward than a random policy.

        In other words, perform a basic check on the imitation learning
        capabilities of AIRLTrainer.
        """
        policy, trainer = _init_trainer(env, use_expert_rollouts=True)
        expert_policy = util.load_expert_policy(env)
        random_policy = util.make_blank_policy(env)
        gen_policy = trainer.policy
        if expert_policy is None:
            pytest.fail("Couldn't load expert_policy!")

        trainer.train(n_epochs=100)

        # Idea: Plot n_epochs vs generator reward.
        for _ in range(4):
            expert_rew = util.rollout_total_reward(expert_policy, env,
                    n_episodes=n_episodes)
            gen_rew = util.rollout_total_reward(gen_policy, env,
                    n_episodes=n_episodes)
            random_rew = util.rollout_total_reward(random_policy, env,
                    n_episodes=n_episodes)

            print("expert reward:", expert_rew)
            print("generator reward:", gen_rew)
            print("random reward:", random_rew)
            assert expert_rew > random_rew
            assert gen_rew > random_rew

    @pytest.mark.expensive
    def test_wrap_learned_reward_no_crash(self, env="CartPole-v1"):
        """
        Briefly train with AIRL, and then used the learned reward to wrap
        a duplicate environment. Finally, use that learned reward to train
        a policy.
        """
        policy, trainer = _init_trainer(env)
        trainer.train(n_epochs=3)
        learned_reward_env = trainer.wrap_env_test_reward(env)
        policy.set_env(learned_reward_env)
        policy.learn(10)
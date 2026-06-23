import React from 'react';
import { StatusBar } from 'expo-status-bar';
import { NavigationContainer } from '@react-navigation/native';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import DashboardScreen from './src/screens/DashboardScreen';
import TestCasesScreen from './src/screens/TestCasesScreen';
import SimulationScreen from './src/screens/SimulationScreen';

const Tab = createBottomTabNavigator();

export default function App() {
  return (
    <NavigationContainer>
      <StatusBar style="light" />
      <Tab.Navigator
        screenOptions={{
          headerStyle: { backgroundColor: '#1a2733' },
          headerTintColor: '#00d4ff',
          tabBarStyle: { backgroundColor: '#1a2733', borderTopColor: 'rgba(0,212,255,0.2)' },
          tabBarActiveTintColor: '#00d4ff',
          tabBarInactiveTintColor: '#7a8fa0',
        }}
      >
        <Tab.Screen name="Dashboard" component={DashboardScreen} />
        <Tab.Screen name="Tests" component={TestCasesScreen} />
        <Tab.Screen name="Simulate" component={SimulationScreen} />
      </Tab.Navigator>
    </NavigationContainer>
  );
}
